#!/usr/bin/env python3
"""Apply the exact Myron CNSS file-selection patch to frozen R79 preparation."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

PREFIX = "vendor/qcom/sm8850-modules/qcom/opensource/wlan/platform/"
EXPECTED_PATHS = {PREFIX + "cnss2/qmi.c", PREFIX + "wlan_platform_modules.bzl"}
HWID_HEADER = "vendor/qcom/sm8850/drivers/misc/hwid/hwid.h"


def pin(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def checked_path(root, relative):
    name = PurePosixPath(relative)
    require(not name.is_absolute() and ".." not in name.parts, "Unsafe input path")
    path = root / name
    require(not path.is_symlink() and path.resolve().is_relative_to(root),
            "Redirected input: " + relative)
    return path


def check_guards(workspace, contract):
    guards = contract["read_only_guards"]
    require(len(guards) == 1 and guards[0]["path"] == HWID_HEADER,
            "Unexpected hwid interface guard")
    row = guards[0]
    data = checked_path(workspace, row["path"]).read_bytes()
    require(pin(data) == row["expected"], "Frozen hwid header changed")
    for name in ("get_hw_version_platform", "get_hw_country_version"):
        require(("uint32_t " + name + "(void);").encode() in data,
                "Actual hwid interface changed: " + name)
    return [{**row, "observed": pin(data)}]


def apply(workspace, route, verify=False):
    workspace, route = Path(workspace).resolve(), Path(route).resolve()
    contract = json.loads((route / "SOURCE-CONTRACT.json").read_text())
    require(contract["schema"] == 1 and contract["source_commit"] ==
            "f2ecb6a09ea56bd8ec9a0bfd2e97f45e200ab322", "Unexpected source revision")
    writes = contract["writes"]
    require(len(writes) == 2 and {r["path"] for r in writes} == EXPECTED_PATHS,
            "Unexpected patch scope")
    patch_row = contract["patch"]
    patch = checked_path(route, patch_row["path"])
    require(pin(patch.read_bytes()) == {k: patch_row[k] for k in ("bytes", "sha256")},
            "Patch content changed")
    guards = check_guards(workspace, contract)
    observations = []
    for row in writes:
        observed = pin(checked_path(workspace, row["path"]).read_bytes())
        require(observed == row["after" if verify else "before"],
                "Unexpected source " + ("postimage: " if verify else "preimage: ") + row["path"])
        observations.append({"path": row["path"], "observed": observed})
    if not verify:
        command = ["patch", "--batch", "--fuzz=0", "--forward", "-p1", "-i", str(patch)]
        subprocess.run(command + ["--dry-run"], cwd=workspace, check=True,
                       text=True, capture_output=True)
        subprocess.run(command, cwd=workspace, check=True, text=True, capture_output=True)
        for row in writes:
            require(pin(checked_path(workspace, row["path"]).read_bytes()) == row["after"],
                    "Patch postimage mismatch: " + row["path"])
    guards = check_guards(workspace, contract)
    return {"schema": 1, "status": "PASS_POSTIMAGES" if verify else "PASS_EXACT_PATCH_APPLIED",
            "source_commit": contract["source_commit"], "patch": patch_row,
            "writes": writes, "read_only_guards": guards,
            "input_observations": observations, "compile_tested": False,
            "hardware_tested": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--route", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(apply(args.workspace, args.route, args.check), indent=2))


if __name__ == "__main__":
    main()
