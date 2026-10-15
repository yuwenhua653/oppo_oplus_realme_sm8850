#!/usr/bin/env python3
"""Retry the unchanged locked synchronizer only after temporary fetch failures.

Three full rounds at most, 30 seconds apart, in the same workspace. The original
synchronizer keeps its HEAD/origin gates and skips already completed projects.
No repository is reset, removed, or moved by this wrapper.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

SYNC_SHA256 = "8df0566d17f4a3b82acea1e13f5db9c66b16fc0788d6bdf72440e46d7ca7c9d1"
LOCK_SHA256 = "ef3d806f679ac8e0bf1371e6ab6dfc173118a32e3a66f44f684116bc0b52e756"
MAX_ROUNDS = 3
RETRY_SECONDS = 30


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pinned_inputs(package):
    for name, expected in (("sync_sources.py", SYNC_SHA256),
                           ("sources.lock.json", LOCK_SHA256)):
        if digest(package / name) != expected:
            raise RuntimeError(f"Pinned input differs: {name}")
    return json.loads((package / "sources.lock.json").read_text())


def temporary_fetch(error, commit):
    """A conservative allowlist; unrelated/hard failure text always wins."""
    prefix = ("Command failed (128): git -c http.version=HTTP/1.1 fetch "
              f"--depth=1 --no-tags origin {commit}\n")
    if not isinstance(error, str) or not error.startswith(prefix):
        return False
    detail = error[len(prefix):]
    hard = (r"returned error: 4\d\d|HTTP(?:/\S+)?\s+4\d\d\b|"
            r"authentication failed|permission denied|could not read username|"
            r"repository not found|couldn't find remote ref|not our ref|"
            r"unadvertised object|certificate|no space left|disk quota|"
            r"read-only file system|cannot create|unable to create|"
            r"unable to write|cannot write|invalid object|bad object")
    if re.search(hard, detail, re.IGNORECASE):
        return False
    if re.search(r"The requested URL returned error: 5\d\d\b", detail):
        return True
    # Git can report a truncated HTTP body without emitting a curl code. The
    # complete combination below occurred in this run's pinned clang fetch.
    # Do not classify generic object/index-pack or early-EOF errors as transient.
    if (re.search(r"\b[1-9][0-9]* bytes of body are still expected\b", detail) and
            "unexpected disconnect while reading sideband packet" in detail and
            "early EOF" in detail):
        return True
    # Require libcurl's explicit error code plus its corresponding transport
    # cause. Generic early-EOF/index-pack errors alone are deliberately rejected.
    transport = {
        6: r"could not resolve host",
        7: r"failed to connect|couldn't connect|could not connect",
        18: r"transfer closed|partial file|end of response|bytes? .*expected",
        28: r"timed out|timeout|too slow",
        52: r"empty reply from server",
        55: r"send failure|failed sending|connection reset",
        56: r"recv failure|receive failure|connection reset|connection was reset|"
            r"TLS connection was non-properly terminated|failed to receive",
    }
    return any(re.search(rf"\bcurl {code}\b[^\n]*({cause})", detail,
                         re.IGNORECASE) for code, cause in transport.items())


def validate_report(report, lock):
    if (report.get("lock_sha256") != LOCK_SHA256 or
            report.get("partial") is not False):
        raise RuntimeError("Fresh sync report has a different lock or is partial")
    expected = {p["path"]: p for p in lock["projects"]}
    if len(expected) != len(lock["projects"]):
        raise RuntimeError("Duplicate locked project")
    successes, errors = report.get("projects"), report.get("errors")
    if not isinstance(successes, list) or not isinstance(errors, list):
        raise RuntimeError("Malformed fresh sync report")
    seen = set()
    for item in successes + errors:
        path = item.get("path")
        if path not in expected or path in seen:
            raise RuntimeError("Unknown or duplicated project in fresh sync report")
        seen.add(path)
    if seen != set(expected):
        raise RuntimeError("Fresh sync report does not account for every locked project")
    for item in successes:
        p = expected[item["path"]]
        if item.get("commit") != p["commit"] or item.get("url") != p["url"]:
            raise RuntimeError("Successful project differs from pinned commit/origin")
    return errors, expected


def execute(package, workspace, jobs, *, runner=subprocess.run, sleeper=time.sleep):
    package, workspace = package.resolve(), workspace.resolve()
    reports = workspace / "integration-reports"
    archive = reports / "sync-retries" / uuid.uuid4().hex
    archive.mkdir(parents=True, exist_ok=False)
    summary = {"sync_sha256": SYNC_SHA256, "lock_sha256": LOCK_SHA256,
               "max_rounds": MAX_ROUNDS, "retry_seconds": RETRY_SECONDS,
               "workspace": str(workspace), "rounds": [], "status": "FAIL"}
    report_path = reports / "sync.json"
    command = [sys.executable, str(package / "sync_sources.py"),
               "--workspace", str(workspace), "--jobs", str(jobs)]
    try:
        lock = pinned_inputs(package)
        if report_path.exists():
            # Preserve but never trust a report from an earlier invocation.
            report_path.rename(archive / "prior-sync.json")
        for number in range(1, MAX_ROUNDS + 1):
            pinned_inputs(package)
            if report_path.exists():
                # The previous round was already archived below.
                report_path.unlink()
            print(f"Locked source sync round {number}/{MAX_ROUNDS}", flush=True)
            result = runner(command, check=False)
            round_dir = archive / f"round-{number}"
            round_dir.mkdir()
            record = {"round": number, "returncode": result.returncode}
            summary["rounds"].append(record)
            if report_path.exists():
                shutil.copy2(report_path, round_dir / "sync.json")
            logs = reports / "sync"
            if logs.exists():
                shutil.copytree(logs, round_dir / "sync")
            pinned_inputs(package)
            if not report_path.is_file():
                raise RuntimeError("Synchronizer did not produce a fresh sync.json")
            report = json.loads(report_path.read_text())
            errors, expected = validate_report(report, lock)
            record["error_paths"] = [e["path"] for e in errors]
            if result.returncode == 0:
                if errors:
                    raise RuntimeError("Synchronizer returned success with reported errors")
                summary["status"] = "PASS"
                print("Every locked project and source link synchronized", flush=True)
                return 0
            if not errors:
                raise RuntimeError("Synchronizer failed outside project fetch (possibly source links)")
            eligible = all(temporary_fetch(e.get("error"), expected[e["path"]]["commit"])
                           for e in errors)
            record["all_errors_temporary_fetch"] = eligible
            if not eligible:
                raise RuntimeError("At least one sync failure is not an allowed temporary fetch error")
            if number == MAX_ROUNDS:
                raise RuntimeError("Temporary source-fetch failures exhausted three sync rounds")
            print(f"All {len(errors)} failures are temporary fetch errors; "
                  f"retrying in {RETRY_SECONDS}s with completed projects retained", flush=True)
            sleeper(RETRY_SECONDS)
        raise RuntimeError("Unreachable sync retry state")
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError) as error:
        summary["reason"] = str(error)
        print(f"ERROR: {error}", file=sys.stderr, flush=True)
        return 1
    finally:
        (archive / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        (reports / "sync-retry-summary.json").write_text(json.dumps(summary, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 16:
        parser.error("--jobs must be between 1 and 16")
    return execute(args.package, args.workspace, args.jobs)


if __name__ == "__main__":
    sys.exit(main())
