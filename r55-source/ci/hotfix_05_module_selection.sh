#!/usr/bin/env bash
# Exact shell body from the pinned R18 workflow step: Apply pinned QCOM module replacement policy
set -euo pipefail
cat > "$PACKAGE_DIR/select_module_candidates.py" <<'MODULE_SELECTION'
#!/usr/bin/env python3
"""Select diagnostic QCOM module candidates, retaining all built originals.

The pinned QCOM build excludes its zram/zsmalloc GKI counterparts from the
runtime distribution. This policy is deliberately limited to the two verified
output pairs. It is not an autoload list or a flashable partition manifest.
"""
import argparse
import collections
import json
from pathlib import Path, PurePosixPath
import re

POLICY = "myron-qcom-zram-v1"
BASE = "bazel-out/aarch64-fastbuild/bin/"
OVERRIDES = {
    "zram": {
        "reference": BASE + "common/kernel_aarch64/drivers/block/zram/zram.ko",
        "selected": BASE + "vendor/qcom/sm8850/canoe_perf/drivers/block/zram/zram/zram.ko",
    },
    "zsmalloc": {
        "reference": BASE + "common/kernel_aarch64/mm/zsmalloc.ko",
        "selected": BASE + "vendor/qcom/sm8850/canoe_perf/mm/zsmalloc/zsmalloc.ko",
    },
}
NOTE = ("Diagnostic candidate selection only: all originals remain in objects/. "
        "Not a module autoload list, partition layout, flash package, or hardware validation.")


def build_selection(modules):
    """Return a selection bound to every input file's path, name, hash and vermagic."""
    modules = sorted(modules, key=lambda item: item["file"])
    if not modules:
        raise ValueError("No modules to select")
    by_name = collections.defaultdict(list)
    files = set()
    for module in modules:
        filename = module["file"]
        path = PurePosixPath(filename)
        if path.is_absolute() or ".." in path.parts or str(path) != filename or path.suffix != ".ko":
            raise ValueError("Unsafe or noncanonical module path: " + filename)
        if filename in files:
            raise ValueError("Repeated module path: " + filename)
        if not re.fullmatch(r"[0-9a-f]{64}", module["sha256"]):
            raise ValueError("Invalid module SHA256: " + filename)
        if not module["vermagic"].strip():
            raise ValueError("Missing module vermagic: " + filename)
        files.add(filename)
        by_name[module["name"]].append(module)
    excluded = []
    for name, expected in OVERRIDES.items():
        pair = by_name.get(name, [])
        if len(pair) != 2 or {item["file"] for item in pair} != set(expected.values()):
            raise ValueError("Expected exactly the pinned common/QCOM pair for " + name)
        if len({item["vermagic"] for item in pair}) != 1:
            raise ValueError("Common/QCOM vermagic differs for " + name)
        excluded.append({
            "file": expected["reference"], "name": name,
            "selected_instead": expected["selected"],
            "reason": "Pinned QCOM module override; retain the GKI original for reference only.",
        })
    # Never turn this policy into a blanket duplicate exception.
    for name, group in by_name.items():
        if name not in OVERRIDES and len({item["sha256"] for item in group}) > 1:
            raise ValueError("Unapproved conflicting duplicate module: " + name)
    excluded_files = {item["file"] for item in excluded}
    return {
        "schema_version": 1, "policy": POLICY,
        "flashable": False, "hardware_tested": False, "note": NOTE,
        "all_built": [{key: item[key] for key in ("file", "name", "sha256", "vermagic")}
                      for item in modules],
        "selected": [item["file"] for item in modules if item["file"] not in excluded_files],
        "excluded": sorted(excluded, key=lambda item: item["file"]),
    }


def validate_selection(modules, selection):
    """Reject stale hashes, extra exclusions, path substitutions or missing inputs."""
    expected = build_selection(modules)
    if selection != expected:
        raise ValueError("Selection manifest differs from the explicit pinned policy or current module files")
    wanted = set(expected["selected"])
    return [module for module in modules if module["file"] in wanted]


def main():
    # Import only for CLI parsing; the dependency gate imports this policy too.
    from check_module_dependencies import modinfo
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        parser.error("module root is not a directory")
    modules = [dict(file=str(path.relative_to(root)), **modinfo(path))
               for path in sorted(root.rglob("*.ko"))]
    selection = build_selection(modules)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(selection, indent=2) + "\n")
    print(json.dumps({"policy": POLICY, "all_built": len(modules),
                      "selected": len(selection["selected"]),
                      "reference_only": len(selection["excluded"]), "flashable": False}))


if __name__ == "__main__":
    main()
MODULE_SELECTION
python3 - <<'PYTHON'
import hashlib
import json
import os
from pathlib import Path

package = Path(os.environ["PACKAGE_DIR"])
workspace = Path(os.environ["WORKSPACE_DIR"])
selector = package / "select_module_candidates.py"
selector_sha256 = '8ceea88b1fd4229b9412139b82a86e1e936515af3b3ad8a3a0210888ee7c1e1e'
source_hashes = {'common/modules.bzl': '4f67b55c9f22db8c7c1dc23cfaeba1f3d12b6a0c5580d60d0fa589b7c40e8f44', 'vendor/qcom/sm8850/kleaf-scripts/android_build.bzl': 'f37f6de851941b9f9e282d5cfcb00fe6b5db372eb1caedf721192aeba94b5877', 'vendor/qcom/sm8850/kleaf-scripts/modules_unprotected.bzl': 'ea4c10f3f16c8a139c0c2c954ab44e8dc08db62f21aadcffe74dc904e607a4a8', 'vendor/qcom/sm8850/modules-lists/modules.systemdlkm_blocklist.msm.canoe': 'f6374c5b9af8adda2a7d860fb050562c0a45cf4229c214d3f185c3a38e7a85b2'}
if hashlib.sha256(selector.read_bytes()).hexdigest() != selector_sha256:
    raise SystemExit("Module selector checksum mismatch")
compile(selector.read_bytes(), str(selector), "exec")
policy_checks = []
for name, expected in source_hashes.items():
    path = workspace / name
    actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    policy_checks.append({"path": name, "expected_sha256": expected,
                          "actual_sha256": actual, "matches": actual == expected})
policy_report = workspace / "integration-reports/upstream-policy-check.json"
policy_report.parent.mkdir(parents=True, exist_ok=True)
policy_report.write_text(json.dumps({"files": policy_checks}, indent=2) + "\n")
mismatches = [entry for entry in policy_checks if not entry["matches"]]
if mismatches:
    raise SystemExit("Unexpected upstream module override policy: " + json.dumps(mismatches))
edits = [
    {
        "path": 'build_platform.py',
        "before": 'ed5135492a876d3b382b131b8ea8a0787bd1001d2b729c46df680071afbdfe62',
        "after": '8f8bf7d96dc1e29b942e4f03891e1bb6a04aee0b3bb9890919e1ff948c739181',
        "replacements": [
            (
                '                "flashable": False, "kernel": "6.12.81-android16 / KMI generation 6",\n                "note": "Source-build diagnostics. No OEM partition image or AK3 is produced."}\n    (dest / "artifact-manifest.json").write_text(json.dumps(manifest, indent=2) + "\\n")\n    (dest / "NOT-A-FLASH-PACKAGE.txt").write_text("开发构建产物，尚未完成 myron 驱动覆盖、分区装配或实机验证。不能套用之前 r38 测试包的刷入步骤。\\n")\n    if missing:\n',
                '                "flashable": False, "kernel": "6.12.81-android16 / KMI generation 6",\n                "module_inventory": "All built originals; consult module-selection.json for the diagnostic candidate set.",\n                "note": "Source-build diagnostics. No OEM partition image or AK3 is produced."}\n    (dest / "artifact-manifest.json").write_text(json.dumps(manifest, indent=2) + "\\n")\n    (dest / "NOT-A-FLASH-PACKAGE.txt").write_text("开发构建产物，尚未完成 myron 驱动覆盖、分区装配或实机验证。不能套用之前 r38 测试包的刷入步骤。objects 保留全部编译原件，包含同名替代模块；请先看 module-selection.json，不可直接铺平复制或全部加载。\\n")\n    if missing:\n',
            ),
            (
                '        (dest / "gki-provenance.json").write_text(json.dumps(provenance, indent=2) + "\\n")\n        report = root / "integration-reports" / (stage + "-module-dependencies.json")\n',
                '        (dest / "gki-provenance.json").write_text(json.dumps(provenance, indent=2) + "\\n")\n        selection = dest / "module-selection.json"\n        selection_report = root / "integration-reports" / (stage + "-module-selection.json")\n        try:\n            logged([sys.executable, str(HERE / "select_module_candidates.py"),\n                    "--root", str(dest / "objects"), "--output", str(selection)],\n                   root, selection_report.with_suffix(".log"))\n        finally:\n            if selection.is_file():\n                shutil.copy2(selection, selection_report)\n        report = root / "integration-reports" / (stage + "-module-dependencies.json")\n',
            ),
            (
                '                    "--release-file", str(release_file), "--builtin-file", str(builtin_file),\n                    "--require-metadata"], root, report.with_suffix(".log"))\n        finally:\n',
                '                    "--release-file", str(release_file), "--builtin-file", str(builtin_file),\n                    "--require-metadata", "--selection-file", str(selection)], root, report.with_suffix(".log"))\n        finally:\n',
            ),
            (
                '    reports.mkdir(parents=True, exist_ok=True)\n    status = {"stage": args.stage, "target": TARGETS[args.stage], "success": False,\n',
                '    reports.mkdir(parents=True, exist_ok=True)\n    # Do not present an earlier successful selection/audit after a failed retry.\n    for suffix in ("-module-selection.json", "-module-selection.log",\n                   "-module-dependencies.json", "-module-dependencies.log"):\n        (reports / (args.stage + suffix)).unlink(missing_ok=True)\n    status = {"stage": args.stage, "target": TARGETS[args.stage], "success": False,\n',
            ),
        ],
    },
    {
        "path": 'check_module_dependencies.py',
        "before": '863ff6b8c955ce960afa85c8f16e4438260dad9bcaeabd59f07031f47c73ac11',
        "after": 'd816c6e5e00ee6fec209b9511fa5906385d6f97c6c0599854b944ca7bb161344',
        "replacements": [
            (
                '\ndef audit(root, release_file=None, builtin_file=None, require_metadata=False, kernel_release=None):\n    root = Path(root).resolve()\n',
                '\ndef audit(root, release_file=None, builtin_file=None, require_metadata=False, kernel_release=None,\n          selection_file=None):\n    root = Path(root).resolve()\n',
            ),
            (
                '        errors.append({"kind": "no_modules"})\n\n',
                '        errors.append({"kind": "no_modules"})\n\n    selected_modules = modules\n    selection = None\n    if selection_file is not None:\n        # This is an explicit opt-in. The default still audits every original\n        # strictly, including rejecting different binaries with the same name.\n        try:\n            from select_module_candidates import validate_selection\n            selection = json.loads(Path(selection_file).read_text())\n            selected_modules = validate_selection(modules, selection)\n        except (ValueError, OSError, KeyError, TypeError) as exc:\n            selection = None\n            errors.append({"kind": "invalid_selection", "error": str(exc)})\n\n',
            ),
            (
                '    duplicates = []\n    for name, group in sorted(by_name.items()):\n',
                '    duplicates = []\n    selected_files = {module["file"] for module in selected_modules}\n    for name, group in sorted(by_name.items()):\n',
            ),
            (
                '            if not entry["identical"]:\n                errors.append(dict(kind="conflicting_duplicate_module", **entry))\n\n',
                '            if not entry["identical"]:\n                chosen = [module["file"] for module in group if module["file"] in selected_files]\n                if selection is not None and len(chosen) == 1:\n                    entry["resolution"] = {"policy": selection["policy"], "selected": chosen[0],\n                                           "reference_only": [module["file"] for module in group\n                                                              if module["file"] not in selected_files]}\n                else:\n                    errors.append(dict(kind="conflicting_duplicate_module", **entry))\n\n',
            ),
            (
                '    builtin_dependencies = collections.defaultdict(set)\n    for module in modules:\n        for dependency in module["depends"]:\n            if dependency in by_name:\n                continue\n',
                '    builtin_dependencies = collections.defaultdict(set)\n    selected_names = {module["name"] for module in selected_modules}\n    for module in selected_modules:\n        for dependency in module["depends"]:\n            if dependency in selected_names:\n                continue\n',
            ),
            (
                '        "success": not errors,\n        "scope": "Static collected-module dependency and vermagic check; no CRC, signature or hardware validation.",\n        "root": str(root), "metadata": metadata, "kernel_releases": sorted(releases),\n        "module_files": len(modules), "unique_modules": len(by_name),\n        "builtin_modules": len(builtins),\n',
                '        "success": not errors,\n        "scope": "Static diagnostic candidate dependency and all-built vermagic check; no CRC, signature or hardware validation. Not an autoload list or flash package.",\n        "root": str(root), "metadata": metadata, "kernel_releases": sorted(releases),\n        "module_files": len(modules), "unique_modules": len(by_name),\n        "selected_module_files": len(selected_modules), "selected_unique_modules": len(selected_names),\n        "selection_policy": selection["policy"] if selection is not None else None,\n        "reference_only": selection["excluded"] if selection is not None else [],\n        "builtin_modules": len(builtins),\n',
            ),
            (
                '        "modules": modules,\n    }\n',
                '        "modules": modules,\n        "selected_modules": [module["file"] for module in selected_modules],\n    }\n',
            ),
            (
                '    parser.add_argument("--require-metadata", action="store_true")\n    args = parser.parse_args()\n    try:\n        report = audit(args.root, args.release_file, args.builtin_file, args.require_metadata, args.kernel_release)\n    except (OSError, ValueError) as exc:\n',
                '    parser.add_argument("--require-metadata", action="store_true")\n    parser.add_argument("--selection-file", type=Path,\n                        help="Explicit pinned QCOM diagnostic selection; defaults to strict all-built audit")\n    args = parser.parse_args()\n    try:\n        report = audit(args.root, args.release_file, args.builtin_file, args.require_metadata, args.kernel_release,\n                       args.selection_file)\n    except (OSError, ValueError) as exc:\n',
            ),
        ],
    },
]
pending, records = [], []
for edit in edits:
    path = package / edit["path"]
    data = path.read_bytes()
    current = hashlib.sha256(data).hexdigest()
    if current == edit["after"]:
        records.append({"path": edit["path"], "status": "already_applied", "sha256": current})
        continue
    if current != edit["before"]:
        raise SystemExit("Unexpected module selection input: " + edit["path"])
    for old, new in edit["replacements"]:
        old, new = old.encode(), new.encode()
        if data.count(old) != 1:
            raise SystemExit("Ambiguous module selection edit: " + edit["path"])
        data = data.replace(old, new, 1)
    if hashlib.sha256(data).hexdigest() != edit["after"]:
        raise SystemExit("Module selection output checksum mismatch: " + edit["path"])
    compile(data, str(path), "exec")
    pending.append((path, data))
    records.append({"path": edit["path"], "status": "applied", "sha256": edit["after"]})
for path, data in pending:
    path.write_bytes(data)
report = workspace / "integration-reports/module-selection-hotfix.json"
report.parent.mkdir(parents=True, exist_ok=True)
report.write_text(json.dumps({
    "hotfix": "r1-qcom-module-selection-fix5", "files": records,
    "selector_sha256": selector_sha256, "upstream_policy_sha256": source_hashes,
    "policy": "Only the pinned zram/zsmalloc pairs select QCOM providers; preserve every built original.",
    "hardware_tested": False,
}, indent=2) + "\n")
print("Pinned QCOM zram/zsmalloc candidate selection enabled; all original modules retained.")
PYTHON
