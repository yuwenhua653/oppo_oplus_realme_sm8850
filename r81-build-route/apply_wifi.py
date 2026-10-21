#!/usr/bin/env python3
"""Apply the exact two-source R81 AP-EDCA trial to a locked kernel workspace."""
import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
import subprocess


PREFIX = "vendor/qcom/sm8850-modules/qcom/opensource/wlan/qcacld-3.0/"
EXPECTED_PATHS = {
    PREFIX + "core/mac/src/pe/sch/sch_beacon_process.c",
    PREFIX + "core/mac/src/pe/lim/lim_utils.c",
}


def pin(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def extract_function(source, name):
    pattern = (r"^(?:static\s+)?(?:void|uint8_t|QDF_STATUS)\s+" +
               re.escape(name) + r"\s*\([^;{}]*\)\s*\{")
    matches = list(re.finditer(pattern, source, re.M))
    require(len(matches) == 1, "Ambiguous function guard: " + name)
    match = matches[0]
    start = source.index("{", match.start())
    depth, end = 1, start + 1
    while depth:
        if source[end] == "{":
            depth += 1
        elif source[end] == "}":
            depth -= 1
        end += 1
    return source[match.start():end].encode()


def check_guards(workspace, contract):
    expected = {
        ("file", PREFIX + "core/sme/src/common/sme_api.c", None),
        ("function", PREFIX + "core/mac/src/pe/lim/lim_utils.c",
         "lim_populate_mcs_set_ht_per_vdev"),
        ("function", PREFIX + "core/mac/src/pe/lim/lim_utils.c",
         "lim_send_ht_caps_ie"),
    }
    rows = contract["read_only_guards"]
    require(len(rows) == len(expected) and
            {(r["kind"], r["path"], r.get("function")) for r in rows} == expected,
            "Unexpected normal-NSS guard scope")
    observations = []
    for row in rows:
        path = workspace / row["path"]
        require(not path.is_symlink() and path.resolve().is_relative_to(workspace),
                "Redirected guard: " + row["path"])
        data = path.read_bytes()
        if row["kind"] == "function":
            data = extract_function(data.decode(), row["function"])
        observed = pin(data)
        require(observed == row["expected"],
                "R79 normal-NSS guard mismatch: " + row["path"] + " " + row.get("function", ""))
        observations.append({**row, "observed": observed})
    return observations


def apply(workspace, repo, verify=False):
    workspace = Path(workspace).resolve()
    repo = Path(repo).resolve()
    contract = json.loads((repo / "SOURCE-CONTRACT.json").read_text())
    require(contract["schema"] == 1 and contract["source_commit"] ==
            "f2ecb6a09ea56bd8ec9a0bfd2e97f45e200ab322", "Unexpected source contract")
    writes = contract["writes"]
    require(len(writes) == 2 and {r["path"] for r in writes} == EXPECTED_PATHS,
            "Unexpected source scope")
    patch_row = contract["patch"]
    patch_name = PurePosixPath(patch_row["path"])
    require(not patch_name.is_absolute() and ".." not in patch_name.parts,
            "Unsafe patch path")
    patch = repo / patch_name
    require(not patch.is_symlink() and patch.resolve().is_relative_to(repo),
            "Redirected patch")
    require(pin(patch.read_bytes()) == {k: patch_row[k] for k in ("bytes", "sha256")},
            "Patch content changed")
    guards = check_guards(workspace, contract)
    state = []
    for row in writes:
        path = workspace / row["path"]
        require(not path.is_symlink() and path.resolve().is_relative_to(workspace),
                "Redirected source: " + row["path"])
        actual = pin(path.read_bytes())
        required = row["after"] if verify else row["before"]
        require(actual == required, "Unexpected source " + ("postimage: " if verify else "preimage: ") + row["path"])
        state.append({"path": row["path"], "observed": actual})
    if not verify:
        command = ["patch", "--batch", "--fuzz=0", "--forward", "-p1", "-i", str(patch)]
        subprocess.run(command + ["--dry-run"], cwd=workspace, check=True,
                       text=True, capture_output=True)
        subprocess.run(command, cwd=workspace, check=True,
                       text=True, capture_output=True)
        for row in writes:
            require(pin((workspace / row["path"]).read_bytes()) == row["after"],
                    "Patch postimage mismatch: " + row["path"])
    guards = check_guards(workspace, contract)
    return {"schema": 1, "status": "PASS_POSTIMAGES" if verify else "PASS_EXACT_PATCH_APPLIED",
            "source_commit": contract["source_commit"], "patch": patch_row,
            "writes": writes, "read_only_guards": guards, "input_observations": state,
            "compile_tested": False, "hardware_tested": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(apply(args.workspace, args.repo, args.check), indent=2))


if __name__ == "__main__":
    main()
