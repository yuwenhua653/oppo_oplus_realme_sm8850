#!/usr/bin/env python3
"""Apply only the reviewed bounded-cache patch to the exact R75 MCA client."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

SOURCE = 'vendor/qcom/sm8850/drivers/power/supply/myron_mca_readonly/myron_mca_readonly.c'
BASE_COMMIT = '45405ec4b75ac71c60f3178d1be24db312fae3ff'
GUARDS = {
    'vendor/qcom/sm8850/drivers/soc/qcom/qti_pmic_glink.c': {'bytes': 25870, 'sha256': 'e766099f52c4905cef5b79e9b8203afbd33aaf303f60c6856d75fb9fb3299999'},
    'vendor/qcom/sm8850/include/linux/soc/qcom/qti_pmic_glink.h': {'bytes': 2788, 'sha256': 'b12e923464df2b0f46a872d7be168856adaac0e00b2d7c83c123fc18f5418baa'},
}


def pin(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def checked_path(root, relative):
    name = PurePosixPath(relative)
    require(not name.is_absolute() and '..' not in name.parts, 'Unsafe input path')
    path = root / name
    require(not path.is_symlink() and path.resolve().is_relative_to(root), 'Redirected input: ' + relative)
    return path


def check_guards(workspace, contract):
    guards = contract['read_only_guards']
    require(len(guards) == len(GUARDS) and {row['path'] for row in guards} == set(GUARDS), 'Unexpected transport guard scope')
    for row in guards:
        require(row['expected'] == GUARDS[row['path']], 'Changed frozen transport guard')
        require(pin(checked_path(workspace, row['path']).read_bytes()) == row['expected'], 'Frozen transport source changed: ' + row['path'])
    return guards


def apply(workspace, route, verify=False):
    workspace, route = Path(workspace).resolve(), Path(route).resolve()
    contract = json.loads((route / 'SOURCE-CONTRACT.json').read_text())
    require(contract['schema'] == 1 and contract['source_commit'] == BASE_COMMIT, 'Unexpected source revision')
    writes = contract['writes']
    require(len(writes) == 1 and writes[0]['path'] == SOURCE, 'Unexpected MCA patch scope')
    patch_row = contract['patch']
    patch = checked_path(route, patch_row['path'])
    require(pin(patch.read_bytes()) == {key: patch_row[key] for key in ('bytes', 'sha256')}, 'Patch content changed')
    check_guards(workspace, contract)
    for row in writes:
        require(pin(checked_path(workspace, row['path']).read_bytes()) == row['after' if verify else 'before'], 'Unexpected source ' + ('postimage' if verify else 'preimage') + ': ' + row['path'])
    if not verify:
        command = ['patch', '--batch', '--fuzz=0', '--forward', '-p1', '-i', str(patch)]
        subprocess.run(command + ['--dry-run'], cwd=workspace / 'vendor/qcom/sm8850', check=True, text=True, capture_output=True)
        subprocess.run(command, cwd=workspace / 'vendor/qcom/sm8850', check=True, text=True, capture_output=True)
        for row in writes:
            require(pin(checked_path(workspace, row['path']).read_bytes()) == row['after'], 'Patch postimage mismatch: ' + row['path'])
    return {'schema': 1, 'status': 'PASS_POSTIMAGES' if verify else 'PASS_EXACT_PATCH_APPLIED', 'source_commit': BASE_COMMIT, 'patch': patch_row, 'writes': writes, 'read_only_guards': check_guards(workspace, contract), 'compile_tested': False, 'hardware_tested': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--route', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(json.dumps(apply(args.workspace, args.route, args.check), indent=2))
