#!/usr/bin/env bash
# Exact shell body from the pinned R18 workflow step: Enable QCOM DDK header profile and batch diagnostics
set -euo pipefail
python3 - <<'PYTHON'
import hashlib
import json
import os
from pathlib import Path

package = Path(os.environ["PACKAGE_DIR"])
workspace = Path(os.environ["WORKSPACE_DIR"])
runner = package / "build_platform.py"
# Match the reviewed runner after the existing progress hotfix.
before = '0cfc2318dcd5755cce2be2093179d00b55436ef5588cfd41ff7549b065b79059'
after = '323956fce205b94d0a4d00b1a81cbd9d2ff051fda66728fbeeb81c9ea970d09d'
replacements = [
    (
        '                 "--output_base=" + str(root / "out/bazel-integration")]\n        options = ["--cpu=aarch64", f"--jobs={args.jobs}", f"--local_ram_resources={args.ram_mb}", "--color=no", "--curses=no", "--show_progress", "--show_progress_rate_limit=30", "--progress_report_interval=30"]\n        # Only traverse this diagnostic graph. No ABL, boot/vendor_boot or dlkm image targets.\n',
        '                 "--output_base=" + str(root / "out/bazel-integration")]\n        # QCOM\'s DDK modules require the internal ACK headers declared by the\n        # pinned SoC tree. The standalone workspace does not import device.bazelrc.\n        # Reuse the same configuration for build and cquery so collected paths\n        # refer to the outputs that were actually compiled.\n        configuration = [\n            "--cpu=aarch64",\n            "--//build/kernel/kleaf:allow_ddk_unsafe_headers",\n            "--//build/kernel/kleaf:user_ddk_unsafe_headers=//vendor/qcom/sm8850:unsafe_headers_qcom_group",\n        ]\n        options = configuration + [f"--jobs={args.jobs}", f"--local_ram_resources={args.ram_mb}", "--color=no", "--curses=no", "--show_progress", "--show_progress_rate_limit=30", "--progress_report_interval=30", "--keep_going"]\n        # Only traverse this diagnostic graph. No ABL, boot/vendor_boot or dlkm image targets.\n',
    ),
    (
        '        if args.stage != "analyze":\n            output = subprocess.run(bazel + ["cquery", "--cpu=aarch64", "--output=files", "--color=no", "--curses=no", TARGETS[args.stage]],\n                                    cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)\n',
        '        if args.stage != "analyze":\n            output = subprocess.run(bazel + ["cquery"] + configuration + ["--output=files", "--color=no", "--curses=no", TARGETS[args.stage]],\n                                    cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)\n',
    ),
]
data = runner.read_bytes()
current = hashlib.sha256(data).hexdigest()
if current == after:
    status = "already_applied"
elif current == before:
    fixed = data
    for old, new in replacements:
        old, new = old.encode(), new.encode()
        if fixed.count(old) != 1:
            raise SystemExit("Ambiguous DDK runner correction")
        fixed = fixed.replace(old, new, 1)
    if hashlib.sha256(fixed).hexdigest() != after:
        raise SystemExit("DDK runner checksum mismatch")
    compile(fixed, str(runner), "exec")
    runner.write_bytes(fixed)
    status = "applied"
else:
    raise SystemExit("Unexpected build runner contents; refusing DDK correction")
report = workspace / "integration-reports/ddk-header-profile-hotfix.json"
report.parent.mkdir(parents=True, exist_ok=True)
report.write_text(json.dumps({
    "hotfix": "r1-ddk-header-profile-fix3",
    "status": status,
    "runner_sha256": after,
    "header_group": "//vendor/qcom/sm8850:unsafe_headers_qcom_group",
    "build_and_cquery_same_configuration": True,
    "keep_going": True,
}, indent=2) + "\n")
print("QCOM DDK header profile enabled for build and cquery; independent failures will be collected in one run.")
PYTHON
