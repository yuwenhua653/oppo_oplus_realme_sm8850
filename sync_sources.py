#!/usr/bin/env python3
"""Fetch the exact public source revisions recorded in sources.lock.json."""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

PACKAGE = Path(__file__).resolve().parent


def run(args, cwd=None, log=None):
    result = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if log:
        log.write("$ " + " ".join(map(str, args)) + "\n" + result.stdout)
        log.flush()
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(map(str, args))}\n{result.stdout[-5000:]}")
    return result.stdout.strip()


def relative(value):
    p = Path(value)
    if p.is_absolute() or not p.parts or any(x in ("..", ".git") for x in p.parts):
        raise ValueError(f"Invalid workspace-relative path: {value}")
    return p


def synchronize(root, project, logs):
    path = root / relative(project["path"])
    commit = project["commit"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Each source must be locked to a full commit")
    url = project["url"]
    if not url.startswith(("https://android.googlesource.com/", "https://github.com/")):
        raise ValueError(f"Unexpected public source: {url}")
    logpath = logs / (project["path"].replace("/", "_") + ".log")
    with logpath.open("w") as log:
        if path.exists() and not (path / ".git").exists():
            if any(path.iterdir()):
                raise RuntimeError(f"Refusing to replace non-repository directory: {path}")
        path.mkdir(parents=True, exist_ok=True)
        if not (path / ".git").exists():
            run(["git", "init", "--quiet", str(path)], log=log)
            run(["git", "remote", "add", "origin", url], cwd=path, log=log)
        actual_url = run(["git", "remote", "get-url", "origin"], cwd=path, log=log)
        if actual_url != url:
            raise RuntimeError(f"Origin differs for {project['path']}: use a new workspace")
        current = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=path,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        if current.returncode == 0:
            if current.stdout.strip() != commit:
                raise RuntimeError(f"HEAD differs for {project['path']}: use a new workspace; no reset was performed")
        else:
            for attempt in range(3):
                try:
                    run(["git", "-c", "http.version=HTTP/1.1", "fetch", "--depth=1", "--no-tags", "origin", commit], cwd=path, log=log)
                    break
                except RuntimeError:
                    if attempt == 2:
                        raise
                    time.sleep(2 * (attempt + 1))
            run(["git", "checkout", "--detach", "--quiet", commit], cwd=path, log=log)
        actual = run(["git", "rev-parse", "HEAD"], cwd=path, log=log)
        if actual != commit:
            raise RuntimeError(f"Commit mismatch: {project['path']}")
        return {"path": project["path"], "commit": actual, "url": url}


def link_sources(root, lock):
    for link in lock["links"]:
        source = root / relative(link["source"])
        target = root / relative(link["destination"])
        if not source.exists():
            raise RuntimeError(f"Missing link source: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        rel = os.path.relpath(source, target.parent)
        if target.is_symlink() and os.readlink(target) == rel:
            continue
        if target.exists() or target.is_symlink():
            raise RuntimeError(f"Refusing to replace existing workspace entry: {target}")
        target.symlink_to(rel)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--only", action="append", default=[], help="Fetch just this locked project; does not mark the workspace complete")
    args = parser.parse_args()
    if not 1 <= args.jobs <= 16:
        parser.error("--jobs must be between 1 and 16")
    raw = (PACKAGE / "sources.lock.json").read_bytes()
    lock = json.loads(raw)
    digest = hashlib.sha256(raw).hexdigest()
    root = args.workspace.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    state = root / ".myron-platform.json"
    if state.exists() and json.loads(state.read_text())["lock_sha256"] != digest:
        raise RuntimeError("This workspace belongs to a different lock; choose a new workspace")
    state.write_text(json.dumps({"lock_sha256": digest, "profile": lock["profile"]}, indent=2) + "\n")
    reports = root / "integration-reports"
    logs = reports / "sync"
    logs.mkdir(parents=True, exist_ok=True)
    projects = lock["projects"]
    if args.only:
        requested = set(args.only)
        if requested - {p["path"] for p in projects}:
            parser.error("--only names a project absent from the lock")
        projects = [p for p in projects if p["path"] in requested]
    results, errors = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(synchronize, root, p, logs): p for p in projects}
        for future in concurrent.futures.as_completed(futures):
            p = futures[future]
            try:
                result = future.result()
                results.append(result)
                print(f"OK {p['path']} {p['commit'][:12]}", flush=True)
            except Exception as error:
                errors.append({"path": p["path"], "error": str(error)})
                print(f"FAIL {p['path']}: {error}", file=sys.stderr, flush=True)
    report = {"lock_sha256": digest, "partial": bool(args.only),
              "projects": sorted(results, key=lambda x: x["path"]), "errors": errors}
    report_name = "sync-partial.json" if args.only else "sync.json"
    (reports / report_name).write_text(json.dumps(report, indent=2) + "\n")
    if errors:
        return 1
    if not args.only:
        link_sources(root, lock)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
