#!/usr/bin/env bash
# Exact shell body from the pinned R18 workflow step: Fix stale QPACE deletion and enable progress
set -euo pipefail
python3 - <<'PYTHON'
import hashlib
import json
import os
from pathlib import Path
import subprocess

workspace = Path(os.environ["WORKSPACE_DIR"])
package = Path(os.environ["PACKAGE_DIR"])
dt = workspace / "vendor/qcom/sm8850-devicetrees"
expected_head = "8b86fedda64183338411f9751f5e62ce25997620"
head = subprocess.check_output(["git", "-C", str(dt), "rev-parse", "HEAD"], text=True).strip()
if head != expected_head:
    raise SystemExit("QPACE hotfix requires the pinned r1 DT revision.")
canoe = dt / "qcom/canoe.dtsi"
if hashlib.sha256(canoe.read_bytes()).hexdigest() != "888b1e020c95f6ab2c186b0433ff9cbc9cc49b1ea4f2fe92edc034fd8274f261":
    raise SystemExit("Unexpected base DT; cannot verify that QPACE was already removed.")

edits = [
    (
        dt / "qcom/alor-interposer-common.dtsi",
        "2fe19c5a4865e7d4e42121af1cccddcb10de0485de95852914abe480883c6926",
        "1db1a0bf08b3422459e6c2f278ad1b9e607fe15b5080ac6514bd78f9a54e5e0a",
        b"/delete-node/ &qcom_qpace;\n",
        b"",
    ),
    (
        package / "build_platform.py",
        "cac195dbffe144b86cb7f16b7af3110e560cb830f9c2e9c47cf5b4bdd2c08009",
        "0cfc2318dcd5755cce2be2093179d00b55436ef5588cfd41ff7549b065b79059",
        b'"--noshow_progress"',
        b'"--show_progress", "--show_progress_rate_limit=30", "--progress_report_interval=30"',
    ),
]
pending = []
records = []
for path, before, after, old, new in edits:
    data = path.read_bytes()
    current = hashlib.sha256(data).hexdigest()
    if current == after:
        records.append({"path": str(path), "status": "already_applied", "sha256": after})
        continue
    if current != before or data.count(old) != 1:
        raise SystemExit("Unexpected contents; refusing to overwrite: " + str(path))
    fixed = data.replace(old, new, 1)
    if hashlib.sha256(fixed).hexdigest() != after:
        raise SystemExit("Hotfix output checksum mismatch: " + str(path))
    pending.append((path, fixed))
    records.append({"path": str(path), "status": "applied", "sha256": after})

# Validate every input before writing any file; reruns accept only exact outputs.
for path, fixed in pending:
    path.write_bytes(fixed)
report = workspace / "integration-reports/qpace-progress-hotfix.json"
report.parent.mkdir(parents=True, exist_ok=True)
report.write_text(json.dumps({
    "hotfix": "r1-qpace-progress-fix1",
    "dt_revision": expected_head,
    "reason": "QPACE node is already absent; remove only its stale delete-node directive.",
    "files": records,
}, indent=2) + "\n")
print("QPACE stale deletion fixed; Bazel progress enabled (30s reports).")
PYTHON
