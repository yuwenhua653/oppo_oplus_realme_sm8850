#!/usr/bin/env bash
# Exact shell body from the pinned R18 workflow step: Collect same-build GKI modules and check dependencies
set -euo pipefail
cat > "$PACKAGE_DIR/check_module_dependencies.py" <<'MODULE_CHECK'
#!/usr/bin/env python3
"""Check collected ARM64 modules as data; never consult host module directories."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import struct


def normalize(name):
    return name.replace("-", "_")


def modinfo(path):
    data = path.read_bytes()
    if len(data) < 64 or data[:7] != b"\x7fELF\x02\x01\x01":
        raise ValueError("expected ELF64 little-endian module")
    if struct.unpack_from("<HH", data, 16) != (1, 183):
        raise ValueError("expected AArch64 ET_REL module")
    offset = struct.unpack_from("<Q", data, 40)[0]
    size, count, names_index = struct.unpack_from("<HHH", data, 58)
    if size != 64 or offset + size > len(data):
        raise ValueError("invalid ELF section table")
    first = struct.unpack_from("<IIQQQQIIQQ", data, offset)
    count = count or first[5]
    names_index = first[6] if names_index == 0xffff else names_index
    if not count or offset + count * size > len(data) or names_index >= count:
        raise ValueError("invalid ELF section count/string table")
    sections = [struct.unpack_from("<IIQQQQIIQQ", data, offset + i * size)
                for i in range(count)]

    def contents(section):
        start, length = section[4:6]
        if start + length > len(data):
            raise ValueError("ELF section extends past end of file")
        return data[start:start + length]

    names = contents(sections[names_index])
    metadata = []
    for section in sections:
        start = section[0]
        end = names.find(b"\0", start)
        if start >= len(names) or end < 0:
            raise ValueError("invalid ELF section name")
        if names[start:end] == b".modinfo":
            metadata.append(contents(section))
    if len(metadata) != 1:
        raise ValueError("expected one .modinfo section")
    fields = collections.defaultdict(list)
    for entry in metadata[0].split(b"\0"):
        if b"=" in entry:
            key, value = entry.decode("utf-8").split("=", 1)
            fields[key].append(value)
    for key in ("name", "vermagic"):
        if len(fields[key]) != 1 or not fields[key][0].strip():
            raise ValueError("missing or ambiguous .modinfo " + key)
    name = normalize(fields["name"][0])
    if not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for c in name):
        raise ValueError("invalid module name")
    return {
        "name": name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "vermagic": " ".join(fields["vermagic"][0].split()),
        "depends": sorted({normalize(d.strip()) for value in fields.get("depends", [])
                           for d in value.split(",") if d.strip()}),
    }


def audit(root, release_file=None, builtin_file=None, require_metadata=False, kernel_release=None):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError("artifact root is not a directory")
    errors, warnings, modules = [], [], []
    for path in sorted(root.rglob("*.ko")):
        file = str(path.relative_to(root))
        try:
            modules.append(dict(file=file, **modinfo(path)))
        except (ValueError, OSError, struct.error) as exc:
            errors.append({"kind": "invalid_module", "file": file, "error": str(exc)})
    if not modules:
        errors.append({"kind": "no_modules"})

    metadata = {}
    def read_metadata(name, explicit):
        paths = [Path(explicit)] if explicit else sorted(root.rglob(name))
        values = []
        for path in paths:
            try:
                value = path.read_text(encoding="utf-8")
                metadata.setdefault(name, []).append(str(path))
                values.append(value)
            except (OSError, UnicodeError) as exc:
                errors.append({"kind": "invalid_metadata", "file": str(path), "error": str(exc)})
        if not values:
            (errors if require_metadata else warnings).append({"kind": "missing_metadata", "file": name})
        return values

    releases = set()
    release_values = [kernel_release] if kernel_release is not None else read_metadata("kernel.release", release_file)
    if kernel_release is not None:
        metadata["kernel.release"] = ["explicit: " + kernel_release]
    for value in release_values:
        if len(value.split()) != 1:
            errors.append({"kind": "invalid_kernel_release", "value": value.strip()})
        else:
            releases.add(value.strip())
    if len(releases) > 1:
        errors.append({"kind": "conflicting_kernel_releases", "values": sorted(releases)})

    builtin_sets = []
    for value in read_metadata("modules.builtin", builtin_file):
        names = set()
        for entry in value.splitlines():
            entry = entry.strip()
            if not entry:
                continue
            if not entry.endswith(".ko"):
                errors.append({"kind": "invalid_builtin_entry", "value": entry})
                continue
            names.add(normalize(Path(entry).stem))
        builtin_sets.append(names)
    if builtin_sets and any(names != builtin_sets[0] for names in builtin_sets[1:]):
        errors.append({"kind": "conflicting_builtin_lists"})
    # Conflicting metadata must not make missing dependencies look satisfied.
    builtins = set.intersection(*builtin_sets) if builtin_sets else set()

    by_name = collections.defaultdict(list)
    by_vermagic = collections.defaultdict(list)
    for module in modules:
        by_name[module["name"]].append(module)
        by_vermagic[module["vermagic"]].append(module["name"])
        release = module["vermagic"].split()[0]
        if releases and release not in releases:
            errors.append({"kind": "kernel_release_mismatch", "module": module["name"],
                           "module_release": release, "kernel_releases": sorted(releases)})
    if len(by_vermagic) > 1:
        errors.append({"kind": "mixed_vermagic", "values": sorted(by_vermagic)})
    duplicates = []
    for name, group in sorted(by_name.items()):
        if len(group) > 1:
            entry = {"module": name, "files": [m["file"] for m in group],
                     "identical": len({m["sha256"] for m in group}) == 1}
            duplicates.append(entry)
            if not entry["identical"]:
                errors.append(dict(kind="conflicting_duplicate_module", **entry))

    missing = collections.defaultdict(set)
    builtin_dependencies = collections.defaultdict(set)
    for module in modules:
        for dependency in module["depends"]:
            if dependency in by_name:
                continue
            if dependency in builtins:
                builtin_dependencies[dependency].add(module["name"])
            else:
                missing[dependency].add(module["name"])
    missing_dependencies = [{"dependency": name, "required_by": sorted(dependents)}
                            for name, dependents in sorted(missing.items())]
    errors.extend(dict(kind="missing_dependency", **entry) for entry in missing_dependencies)
    return {
        "success": not errors,
        "scope": "Static collected-module dependency and vermagic check; no CRC, signature or hardware validation.",
        "root": str(root), "metadata": metadata, "kernel_releases": sorted(releases),
        "module_files": len(modules), "unique_modules": len(by_name),
        "builtin_modules": len(builtins),
        "vermagic": {k: sorted(set(v)) for k, v in sorted(by_vermagic.items())},
        "missing_dependencies": missing_dependencies,
        "builtin_dependencies": {k: sorted(v) for k, v in sorted(builtin_dependencies.items())},
        "duplicates": duplicates, "errors": errors, "warnings": warnings,
        "modules": modules,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    release = parser.add_mutually_exclusive_group()
    release.add_argument("--kernel-release", help="Authoritative GKI release string")
    release.add_argument("--release-file", type=Path, help="Authoritative GKI kernel.release file")
    parser.add_argument("--builtin-file", type=Path, help="Authoritative GKI modules.builtin file")
    parser.add_argument("--require-metadata", action="store_true")
    args = parser.parse_args()
    try:
        report = audit(args.root, args.release_file, args.builtin_file, args.require_metadata, args.kernel_release)
    except (OSError, ValueError) as exc:
        report = {"success": False, "errors": [{"kind": "input_error", "error": str(exc)}]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("success", "module_files", "unique_modules", "missing_dependencies", "errors", "warnings") if k in report}, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
MODULE_CHECK
python3 - <<'PYTHON'
import hashlib
import json
import os
from pathlib import Path

package = Path(os.environ["PACKAGE_DIR"])
workspace = Path(os.environ["WORKSPACE_DIR"])
runner = package / "build_platform.py"
checker = package / "check_module_dependencies.py"
before = '323956fce205b94d0a4d00b1a81cbd9d2ff051fda66728fbeeb81c9ea970d09d'
after = 'ed5135492a876d3b382b131b8ea8a0787bd1001d2b729c46df680071afbdfe62'
checker_sha256 = '863ff6b8c955ce960afa85c8f16e4438260dad9bcaeabd59f07031f47c73ac11'
if hashlib.sha256(checker.read_bytes()).hexdigest() != checker_sha256:
    raise SystemExit("Module dependency checker checksum mismatch")
compile(checker.read_bytes(), str(checker), "exec")
replacements = [
    (
        '}\n\n',
        '}\n\n\nGKI_TARGETS = [\n    "//common:kernel_aarch64_modules",\n    "//myron_artifact_metadata:kernel_release",\n]\nGKI_METADATA_BUILD = \'# Generated by the Myron diagnostic runner; exposes only existing GKI output.\\nfilegroup(\\n    name = "kernel_release",\\n    srcs = ["//common:kernel_aarch64"],\\n    output_group = "include/config/kernel.release",\\n)\\n\'\n\n\ndef build_targets(root, stage):\n    targets = [TARGETS[stage]]\n    if stage in ("analyze", "soc", "full"):\n        definition = root / "myron_artifact_metadata/BUILD.bazel"\n        if definition.exists() and definition.read_text() != GKI_METADATA_BUILD:\n            raise RuntimeError("Unexpected generated GKI metadata target contents")\n        definition.parent.mkdir(parents=True, exist_ok=True)\n        definition.write_text(GKI_METADATA_BUILD)\n        targets += GKI_TARGETS\n    return targets\n\n',
    ),
    (
        '    dest = root / "integration-artifacts" / stage\n    dest.mkdir(parents=True, exist_ok=True)\n    items = []\n    for name in paths:\n        source = root / name\n        if not source.is_file():\n            continue\n        if not (source.suffix in (".ko", ".dtb", ".dtbo", ".symvers") or\n                source.name in ("Image", "Image.gz", "Image.lz4", ".config", "System.map", "kernel.release")):\n            continue\n        rel = Path(name)\n',
        '    dest = root / "integration-artifacts" / stage\n    # A previous attempt must not supply missing providers to this attempt\'s audit.\n    if dest.exists():\n        shutil.rmtree(dest)\n    dest.mkdir(parents=True, exist_ok=True)\n    items = []\n    for name in dict.fromkeys(paths):\n        rel = Path(name)\n',
    ),
    (
        '            raise ValueError("Unexpected Bazel output path: " + name)\n        target = dest / "objects" / rel\n',
        '            raise ValueError("Unexpected Bazel output path: " + name)\n        source = root / rel\n        if not (source.suffix in (".ko", ".dtb", ".dtbo", ".symvers") or\n                source.name in ("Image", "Image.gz", "Image.lz4", ".config", "System.map", "kernel.release",\n                                "modules.builtin", "modules.builtin.modinfo", "kernel_aarch64_dot_config")):\n            continue\n        if not source.is_file():\n            raise RuntimeError("Declared Bazel output is missing: " + name)\n        target = dest / "objects" / rel\n',
    ),
    (
        '    if stage in ("soc", "full"):\n        required |= {"mi_fp.ko", "mi_stack.ko", "mi_ubt.ko", "printk_enhance.ko", "panel_event_notifier.ko", "boot_stats.ko"}\n    if stage in ("dtbs", "full"):\n',
        '    if stage in ("soc", "full"):\n        required |= {"rfkill.ko", "libarc4.ko", "kernel.release", "modules.builtin",\n                     "modules.builtin.modinfo", "kernel_aarch64_dot_config", "mi_fp.ko", "mi_stack.ko", "mi_ubt.ko", "printk_enhance.ko", "panel_event_notifier.ko", "boot_stats.ko"}\n    if stage in ("dtbs", "full"):\n',
    ),
    (
        '        raise RuntimeError("Build finished but required outputs are missing: " + ", ".join(missing))\n    return len(items)\n',
        '        raise RuntimeError("Build finished but required outputs are missing: " + ", ".join(missing))\n    if stage in ("soc", "full"):\n        # Use common\'s metadata, not the separate DTB-build configuration.\n        def gki_file(basename):\n            matches = [dest / item["file"] for item in items\n                       if Path(item["file"]).name == basename and "/common/kernel_aarch64/" in item["source"]]\n            if len(matches) != 1:\n                raise RuntimeError("Expected one authoritative GKI output: " + basename)\n            return matches[0]\n\n        release_file = gki_file("kernel.release")\n        builtin_file = gki_file("modules.builtin")\n        config_file = gki_file("kernel_aarch64_dot_config")\n        image_file = gki_file("Image")\n        release = release_file.read_text().strip()\n        if not release or len(release.split()) != 1 or (b"Linux version " + release.encode() + b" ") not in image_file.read_bytes():\n            raise RuntimeError("Collected GKI release does not match Image banner")\n        gki_modules = [item for item in items if item["file"].endswith(".ko") and "/common/kernel_aarch64/" in item["source"]]\n        if not gki_modules or any(not (dest / item["file"]).read_bytes().endswith(b"~Module signature appended~\\n") for item in gki_modules):\n            raise RuntimeError("Expected installed GKI modules with appended signatures")\n        provenance = {"kernel_release": release, "kernel_release_file": str(release_file.relative_to(dest)),\n                      "image_config": str(config_file.relative_to(dest)), "modules_builtin": str(builtin_file.relative_to(dest)),\n                      "gki_module_count": len(gki_modules), "gki_modules_have_signature_trailer": True,\n                      "gki_module_source": "//common:kernel_aarch64_modules",\n                      "note": "Includes upstream KUnit outputs; this is not a phone module autoload list. Signature cryptography is not verified here."}\n        (dest / "gki-provenance.json").write_text(json.dumps(provenance, indent=2) + "\\n")\n        report = root / "integration-reports" / (stage + "-module-dependencies.json")\n        try:\n            logged([sys.executable, str(HERE / "check_module_dependencies.py"),\n                    "--root", str(dest / "objects"), "--output", str(report),\n                    "--release-file", str(release_file), "--builtin-file", str(builtin_file),\n                    "--require-metadata"], root, report.with_suffix(".log"))\n        finally:\n            if report.is_file():\n                shutil.copy2(report, dest / "module-dependencies.json")\n    return len(items)\n',
    ),
    (
        '        options = configuration + [f"--jobs={args.jobs}", f"--local_ram_resources={args.ram_mb}", "--color=no", "--curses=no", "--show_progress", "--show_progress_rate_limit=30", "--progress_report_interval=30", "--keep_going"]\n        # Only traverse this diagnostic graph. No ABL, boot/vendor_boot or dlkm image targets.\n        command = bazel + ["build"] + options\n',
        '        options = configuration + [f"--jobs={args.jobs}", f"--local_ram_resources={args.ram_mb}", "--color=no", "--curses=no", "--show_progress", "--show_progress_rate_limit=30", "--progress_report_interval=30", "--keep_going"]\n        targets = build_targets(root, args.stage)\n        status["build_targets"] = targets\n        # Include installed GKI modules without selecting any partition image targets.\n        command = bazel + ["build"] + options\n',
    ),
    (
        '            command += ["--nobuild"]\n        command += [TARGETS[args.stage]]\n        logged(command, root, reports / (args.stage + ".log"))\n',
        '            command += ["--nobuild"]\n        command += targets\n        logged(command, root, reports / (args.stage + ".log"))\n',
    ),
    (
        '        if args.stage != "analyze":\n            output = subprocess.run(bazel + ["cquery"] + configuration + ["--output=files", "--color=no", "--curses=no", TARGETS[args.stage]],\n                                    cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)\n',
        '        if args.stage != "analyze":\n            status["compiled"] = True\n            query = "set(" + " ".join(targets) + ")"\n            output = subprocess.run(bazel + ["cquery"] + configuration + ["--output=files", "--color=no", "--curses=no", query],\n                                    cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)\n',
    ),
    (
        '            status["artifact_count"] = collect(root, output.stdout.splitlines(), args.stage)\n            status["compiled"] = True\n        else:\n',
        '            status["artifact_count"] = collect(root, output.stdout.splitlines(), args.stage)\n            if args.stage in ("soc", "full"):\n                status["module_dependencies_passed"] = True\n        else:\n',
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
            raise SystemExit("Ambiguous GKI collection correction")
        fixed = fixed.replace(old, new, 1)
    if hashlib.sha256(fixed).hexdigest() != after:
        raise SystemExit("GKI collection runner checksum mismatch")
    compile(fixed, str(runner), "exec")
    runner.write_bytes(fixed)
    status = "applied"
else:
    raise SystemExit("Unexpected build runner contents; refusing GKI collection correction")
report = workspace / "integration-reports/gki-collection-hotfix.json"
report.parent.mkdir(parents=True, exist_ok=True)
report.write_text(json.dumps({
    "hotfix": "r1-gki-module-collection-fix4",
    "status": status,
    "runner_sha256": after,
    "checker_sha256": checker_sha256,
    "gki_modules": "//common:kernel_aarch64_modules",
    "checks": ["Image release", "GKI signature trailer presence", "module dependencies", "module vermagic"],
    "hardware_tested": False,
}, indent=2) + "\n")
print("Installed GKI modules and authoritative metadata added; module dependency checks enabled.")
PYTHON
