#!/usr/bin/env python3
"""Focused retry-policy and fresh/full source-lock report tests (no network)."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import sync_with_retry as sync


class SyncRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.package, self.workspace = root / "package", root / "workspace"
        self.package.mkdir()
        reference = Path(__file__).parent / "reference/myron-qcom-platform-r1"
        # In CI, extraction already provides the same SHA-pinned package.
        if not reference.is_dir():
            reference = Path(__file__).resolve().parents[1] / "myron-qcom-platform-r1"
        for name in ("sync_sources.py", "sources.lock.json"):
            shutil.copy2(reference / name, self.package / name)
        self.lock = sync.pinned_inputs(self.package)
        self.report_path = self.workspace / "integration-reports/sync.json"
        self.success = {"lock_sha256": sync.LOCK_SHA256, "partial": False,
                        "projects": [{k: p[k] for k in ("path", "commit", "url")}
                                     for p in self.lock["projects"]], "errors": []}

    def failure(self, detail="The requested URL returned error: 503"):
        report = copy.deepcopy(self.success)
        project = report["projects"].pop(0)
        report["errors"].append({"path": project["path"], "error":
            "Command failed (128): git -c http.version=HTTP/1.1 fetch "
            f"--depth=1 --no-tags origin {project['commit']}\n"
            f"fatal: unable to access '{project['url']}': {detail}\n"})
        return report

    def invoke(self, attempts, stale=None, mutate=None):
        if stale is not None:
            self.report_path.parent.mkdir(parents=True)
            self.report_path.write_text(json.dumps(stale))
        calls, waits = [], []
        def runner(command, check):
            self.assertIs(check, False)
            self.assertFalse(self.report_path.exists(), "stale report leaked to new child")
            calls.append(command[:])
            code, report = attempts[len(calls) - 1]
            if report is not None:
                self.report_path.write_text(json.dumps(report))
            if mutate:
                mutate()
            return subprocess.CompletedProcess(command, code)
        result = sync.execute(self.package, self.workspace, 4, runner=runner,
                              sleeper=waits.append)
        summary = json.loads((self.report_path.parent / "sync-retry-summary.json").read_text())
        self.assertEqual(len(set(tuple(c) for c in calls)), min(1, len(calls)))
        for c in calls:
            self.assertEqual(c[2:], ["--workspace", str(self.workspace), "--jobs", "4"])
        return result, calls, waits, summary

    def test_transient_then_success_and_archives(self):
        result, calls, waits, summary = self.invoke([(1, self.failure()), (0, self.success)])
        self.assertEqual((result, len(calls), waits, summary["status"]), (0, 2, [30], "PASS"))
        self.assertEqual(len(list(self.report_path.parent.glob("sync-retries/*/round-*/sync.json"))), 2)

    def test_exhaustion_is_three_rounds_and_two_waits(self):
        result, calls, waits, _ = self.invoke([(1, self.failure())] * 3)
        self.assertEqual((result, len(calls), waits), (1, 3, [30, 30]))

    def test_hard_or_mixed_failures_do_not_retry(self):
        for detail in ("The requested URL returned error: 404",
                       "The requested URL returned error: 503; authentication failed",
                       "RPC failed; curl 56 Recv failure; No space left on device",
                       "early EOF; index-pack failed"):
            with self.subTest(detail=detail):
                result, calls, waits, _ = self.invoke([(1, self.failure(detail))])
                self.assertEqual((result, len(calls), waits), (1, 1, []))

    def test_head_or_mixed_project_error_does_not_retry(self):
        report = self.failure()
        project = report["projects"].pop(0)
        report["errors"].append({"path": project["path"], "error": "HEAD differs; no reset was performed"})
        result, calls, waits, _ = self.invoke([(1, report)])
        self.assertEqual((result, len(calls), waits), (1, 1, []))

    def test_missing_report_and_stale_success_not_accepted(self):
        result, calls, waits, _ = self.invoke([(0, None)], stale=self.success)
        self.assertEqual((result, len(calls), waits), (1, 1, []))
        self.assertEqual(len(list(self.report_path.parent.glob("sync-retries/*/prior-sync.json"))), 1)

    def test_failed_links_do_not_retry_despite_success_report(self):
        result, calls, waits, _ = self.invoke([(1, self.success)])
        self.assertEqual((result, len(calls), waits), (1, 1, []))

    def test_partial_missing_wrong_commit_duplicate_and_wrong_lock_fail(self):
        bad = []
        r = copy.deepcopy(self.success); r["partial"] = True; bad.append(r)
        r = copy.deepcopy(self.success); r["projects"].pop(); bad.append(r)
        r = copy.deepcopy(self.success); r["projects"][0]["commit"] = "0" * 40; bad.append(r)
        r = copy.deepcopy(self.success); r["projects"][0]["url"] += "/different"; bad.append(r)
        r = copy.deepcopy(self.success); r["projects"].append(r["projects"][0]); bad.append(r)
        r = copy.deepcopy(self.success); r["lock_sha256"] = "0" * 64; bad.append(r)
        for report in bad:
            with self.subTest(report=report):
                result, calls, waits, _ = self.invoke([(0, report)])
                self.assertEqual((result, len(calls), waits), (1, 1, []))

    def test_mutation_of_lock_during_child_fails(self):
        def mutate():
            with (self.package / "sources.lock.json").open("a") as f:
                f.write("\n")
        result, calls, waits, _ = self.invoke([(0, self.success)], mutate=mutate)
        self.assertEqual((result, len(calls), waits), (1, 1, []))

    def test_wrong_synchronizer_before_child_is_rejected(self):
        (self.package / "sync_sources.py").write_text("raise Exception('altered')\n")
        result, calls, waits, _ = self.invoke([])
        self.assertEqual((result, len(calls), waits), (1, 0, []))

    def test_explicit_transport_and_wrong_commit_classifier(self):
        project = self.lock["projects"][0]
        for cause in ("RPC failed; curl 28 Operation timed out", "RPC failed; curl 56 Recv failure: Connection reset by peer"):
            error = self.failure(cause)["errors"][0]["error"]
            self.assertTrue(sync.temporary_fetch(error, project["commit"]))
            self.assertFalse(sync.temporary_fetch(error, "0" * 40))

    def test_truncated_http_body_requires_complete_transport_signature(self):
        detail = ("error: 13616 bytes of body are still expected\n"
                  "fetch-pack: unexpected disconnect while reading sideband packet\n"
                  "fatal: early EOF\nfatal: fetch-pack: invalid index-pack output")
        project = self.lock["projects"][0]
        error = self.failure(detail)["errors"][0]["error"]
        self.assertTrue(sync.temporary_fetch(error, project["commit"]))
        self.assertFalse(sync.temporary_fetch(error + "\nNo space left on device", project["commit"]))
        self.assertFalse(sync.temporary_fetch(error.replace("13616 bytes of body are still expected", ""), project["commit"]))
        result, calls, waits, _ = self.invoke([(1, self.failure(detail)), (0, self.success)])
        self.assertEqual((result, len(calls), waits), (0, 2, [30]))


if __name__ == "__main__":
    unittest.main()
