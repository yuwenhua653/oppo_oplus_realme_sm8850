#!/usr/bin/env python3
"""Compile actual observer TU with narrow host APIs; never copy its algorithms."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess


def pin(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("--output must be absent or empty")
    output.mkdir(parents=True, exist_ok=True)
    here = Path(__file__).resolve().parent
    body = source.read_text()
    assert re.findall(r"module_param\((\w+),\s*(\w+),\s*(\d+)\)", body) == [
        ("enable_observer", "bool", "0444")
    ]
    assert "static bool enable_observer;" in body
    forbidden = r"\b(?:EXPORT_SYMBOL(?:_GPL)?|pmic_glink_[a-z_]+|mca_vote|power_supply_register|devm_power_supply_register|power_supply_set_property|thermal_cooling_device_register|thermal_of_cooling_device_register|sysfs_create_link|class_create|device_create|schedule_work|schedule_delayed_work)\s*\("
    assert not re.search(forbidden, body)
    assert "xm_power" not in body
    assert "devm_device_remove_group" not in body
    table = body.split("static const u32 mt_expected[MT_ROWS][MT_COLS] = {", 1)[1].split("};", 1)[0]
    cells = [int(x) for x in re.findall(r"\b\d+\b", table)]
    assert len(cells) == 150
    table_sha = hashlib.sha256(struct.pack(">150I", *cells)).hexdigest()
    assert table_sha == "6539e46407caa74c604290577741c36f730ee0051c1c5bb27698c0422f714bca"
    # Only Linux include directives are removed. Every production function,
    # type, initializer, attribute, and driver lifecycle body is compiled.
    transformed = re.sub(r"^#include <linux/[^>]+>\n", "", body, flags=re.M)
    tu = output / "production_test.c"
    tu.write_text('#include "fake_kernel.h"\n' + transformed + '\n#include "test_receiver.c"\n')
    compiler = os.environ.get("CC") or shutil.which("clang") or shutil.which("gcc")
    if not compiler:
        raise RuntimeError("clang or gcc required")
    binary = output / "test_receiver"
    command = [compiler, "-std=gnu11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
               "-Wno-unused-parameter", "-Wstrict-prototypes", "-Werror=implicit-function-declaration",
               "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-pthread", "-no-pie",
               "-I", str(here), str(tu), "-o", str(binary)]
    built = subprocess.run(command, text=True, capture_output=True, timeout=60)
    (output / "compile.log").write_text(built.stdout + built.stderr)
    if built.returncode:
        raise RuntimeError("production TU host compilation failed; see compile.log")
    # This host does not permit LSan's /proc/<pid>/task walk. ASan/UBSan
    # remain enabled; do not claim leak-sanitizer or real kernel lifetime tests.
    environment = dict(os.environ, ASAN_OPTIONS="detect_leaks=0:halt_on_error=1",
                       UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
    ran = subprocess.run([str(binary)], text=True, capture_output=True, timeout=60, env=environment)
    (output / "run.log").write_text(ran.stdout + ran.stderr)
    if ran.returncode:
        raise RuntimeError("production tests failed; see run.log")
    assert "PASS all 8 production-function groups" in ran.stdout
    report = {
        "status": "PASS", "source_sha256": pin(source)["sha256"], "source": pin(source),
        "tests": 8, "dt_cell_mutations": 150, "concurrent_writes": 8000,
        "whole_translation_unit": True, "transformation": "remove_linux_includes_only",
        "sanitizers": ["ASan", "UBSan"], "strict_prototypes": True,
        "kernel_current_macro_enabled": True, "dt_raw_sha256": table_sha,
        "commands": [command, [str(binary)]],
        "inputs": {name: pin(here / name) for name in ["run_tests.py", "fake_kernel.h", "test_receiver.c"]},
        "limitations": [
            "LeakSanitizer is disabled because this host denies its process task scan; no LSan pass is claimed.",
            "Host API shim tests production logic and callback ordering; it does not establish Linux kernfs lifetime semantics or actual module ABI.",
            "No device, hardware, charging, SELinux, Windows, or kernel hot-unload execution was performed.",
            "Actual kernel 6.12 API/export review and compile-only CI remain separate gates."
        ]
    }
    (output / "RESULT.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "source_sha256": report["source_sha256"], "tests": 8}))


if __name__ == "__main__":
    main()
