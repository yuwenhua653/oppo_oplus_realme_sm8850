#!/usr/bin/env bash
# Exact shell body from the pinned R18 workflow step: Fix Myron DTBO output collection
set -euo pipefail
python3 - <<'PYTHON'
import hashlib
import json
import os
from pathlib import Path

package = Path(os.environ["PACKAGE_DIR"])
workspace = Path(os.environ["WORKSPACE_DIR"])
# Keep the original r1 archive; update only its reviewed DT integration files.
# Basename declarations use Kleaf's recursive lookup from the DT repository root.
edits = [
    {
        'path': 'devicetrees/myron-dt-integration.patch',
        'before_sha256': 'c0934e8cfc229561fa62f7844f6e2cb5e6415ffe261916bb566f0ac75ab5af74',
        'after_sha256': '1eb047983a06ecfae3c88ef06c3ae9f7fd336fc214fc5f8b057e7fba2c2e1571',
        "replacements": [
            (
                '+            # This does not define the OEM dtbo.img table or overlay ordering.\n+            {"name": "audio/myron-audio-mtp.dtbo"},\n+            {"name": "camera/myron-sm8850-camera-sensor.dtbo"},\n+            {"name": "display/display/myron-sde-display-mtp-overlay.dtbo"},\n             {"name": "pandora-sm8850-overlay.dtbo"},\n',
                '+            # This does not define the OEM dtbo.img table or overlay ordering.\n+            {"name": "myron-audio-mtp.dtbo"},\n+            {"name": "myron-sm8850-camera-sensor.dtbo"},\n+            {"name": "myron-sde-display-mtp-overlay.dtbo"},\n             {"name": "pandora-sm8850-overlay.dtbo"},\n',
            ),
        ],
    },
    {
        'path': 'devicetrees/myron-dt-patch-manifest.json',
        'before_sha256': '50abdcf04f749015f2d9cb5324b40b5cff8fb145966e53dd651869c243bc7870',
        'after_sha256': 'f41f9badbdf915563ac6c9c8a9fc6930015a77dad9e1822e4e207cd6e94c6191',
        "replacements": [
            (
                '  },\n  "patch_sha256": "c0934e8cfc229561fa62f7844f6e2cb5e6415ffe261916bb566f0ac75ab5af74",\n  "files": [\n',
                '  },\n  "patch_sha256": "1eb047983a06ecfae3c88ef06c3ae9f7fd336fc214fc5f8b057e7fba2c2e1571",\n  "files": [\n',
            ),
            (
                '      "before_sha256": "38a928850b24444d4d89d7761390e576da72688d3a6f7410d5fa08a7e42d1fac",\n      "after_sha256": "6b107daabc1a5a652d131063ce81cd6fb5a9495760f2c80c3ed1db545e8df2da"\n    },\n',
                '      "before_sha256": "38a928850b24444d4d89d7761390e576da72688d3a6f7410d5fa08a7e42d1fac",\n      "after_sha256": "33a50ccf84bfeb9bb5387322be4c866dda238a9bb58cf4efefdd9e0f088dd357"\n    },\n',
            ),
        ],
    },
    {
        'path': 'devicetrees/check-myron-dt-wiring.py',
        'before_sha256': 'ad31a87102cae09d9c7536abdffc8bfdae41c81315f2d360d6a8e9dcb4cc9317',
        'after_sha256': 'ade0b588932db4f73f013818fb9524cd4b7d48bd30325bbbe05646a21add1130',
        "replacements": [
            (
                '            required.extend(item["name"] for item in platform_map[platform].get(group, []))\n    for name in required:\n        if name not in outputs:\n            raise ValueError("Bazel output absent from Kbuild: " + name)\n        source = dt / "qcom" / name\n        if not any(source.with_suffix(ext).is_file() for ext in (".dts", ".dtso")):\n            raise ValueError("Missing declared DT source: " + name)\n    expected = ["myron-sm8850-overlay.dtbo", "audio/myron-audio-mtp.dtbo",\n                "camera/myron-sm8850-camera-sensor.dtbo",\n                "display/display/myron-sde-display-mtp-overlay.dtbo"]\n    if not set(expected).issubset(required):\n        raise ValueError("A myron component is absent from the Bazel output list")\n    build = (dt / "BUILD.bazel").read_text()\n',
                '            required.extend(item["name"] for item in platform_map[platform].get(group, []))\n    # Kleaf searches from the external DT repository root, not its qcom folder.\n    # Its pinned search_and_cp_output.py treats names with \'/\' as exact paths;\n    # basename-only names are found recursively and must have a unique match.\n    physical_outputs = {"qcom/" + name for name in outputs}\n    resolved_outputs = {}\n    for name in required:\n        if "/" in name:\n            matches = [name] if name in physical_outputs else []\n        else:\n            matches = sorted(path for path in physical_outputs if Path(path).name == name)\n        if len(matches) != 1:\n            raise ValueError("Kleaf output must resolve to one Kbuild file: " +\n                             name + " -> " + repr(matches))\n        resolved_outputs[name] = matches[0]\n        source = dt / matches[0]\n        if not any(source.with_suffix(ext).is_file() for ext in (".dts", ".dtso")):\n            raise ValueError("Missing declared DT source: " + str(source))\n    expected = {\n        "myron-sm8850-overlay.dtbo": "qcom/myron-sm8850-overlay.dtbo",\n        "myron-audio-mtp.dtbo": "qcom/audio/myron-audio-mtp.dtbo",\n        "myron-sm8850-camera-sensor.dtbo": "qcom/camera/myron-sm8850-camera-sensor.dtbo",\n        "myron-sde-display-mtp-overlay.dtbo": "qcom/display/display/myron-sde-display-mtp-overlay.dtbo",\n    }\n    for name, physical_path in expected.items():\n        if resolved_outputs.get(name) != physical_path:\n            raise ValueError("A myron component is absent or misrouted: " + name)\n    build = (dt / "BUILD.bazel").read_text()\n',
            ),
            (
                '            raise ValueError("Missing sandbox input: " + pattern)\n    return {"status": "PASS", "scope": "GNU make and source/output wiring only",\n            "platforms": selected, "main_targets": len(top), "subsystem_targets": subcounts,\n            "declared_outputs_checked": len(required), "myron_components": expected,\n            "dtc_compilation": "NOT_RUN", "hardware_validation": "NOT_RUN",\n',
                '            raise ValueError("Missing sandbox input: " + pattern)\n    return {"status": "PASS", "scope": "GNU make, DT source and Kleaf collection-path contract only",\n            "platforms": selected, "main_targets": len(top), "subsystem_targets": subcounts,\n            "declared_outputs_checked": len(required), "myron_components": list(expected),\n            "kleaf_resolved_outputs": resolved_outputs,\n            "dtc_compilation": "NOT_RUN", "hardware_validation": "NOT_RUN",\n',
            ),
        ],
    },
]
pending = []
records = []
for edit in edits:
    path = package / edit["path"]
    data = path.read_bytes()
    current = hashlib.sha256(data).hexdigest()
    if current == edit["after_sha256"]:
        records.append({"path": edit["path"], "status": "already_applied", "sha256": current})
        continue
    if current != edit["before_sha256"]:
        raise SystemExit("Unexpected DT integration contents: " + str(path))
    fixed = data
    for old, new in edit["replacements"]:
        old, new = old.encode(), new.encode()
        if fixed.count(old) != 1:
            raise SystemExit("Ambiguous DT output correction: " + str(path))
        fixed = fixed.replace(old, new, 1)
    if hashlib.sha256(fixed).hexdigest() != edit["after_sha256"]:
        raise SystemExit("DT output correction checksum mismatch: " + str(path))
    pending.append((path, fixed))
    records.append({"path": edit["path"], "status": "applied", "sha256": edit["after_sha256"]})
for path, fixed in pending:
    path.write_bytes(fixed)
report = workspace / "integration-reports/dt-output-collection-hotfix.json"
report.parent.mkdir(parents=True, exist_ok=True)
report.write_text(json.dumps({
    "hotfix": "r1-dt-output-collection-fix2",
    "reason": "Collect all three subsystem DTBOs by unique basename; validate the Kleaf lookup contract before compiling.",
    "files": records,
}, indent=2) + "\n")
print("Myron DTBO output declarations fixed; collection-path preflight enabled.")
PYTHON
