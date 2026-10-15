#!/usr/bin/env python3
"""Fail before source sync unless a complete reviewed hardware contract is present."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


def check(root, contract):
    if contract.get('schema') != 1 or contract.get('source_review') != 'PASS':
        raise ValueError('Hardware source review is incomplete; do not start a build')
    if contract.get('baseline_kernel_release') != '6.12.81-android16-6-maybe-dirty-4k':
        raise ValueError('Unexpected runtime kernel baseline')
    expected = {
        ('camera', '//vendor/qcom/sm8850-modules/qcom/opensource/camera-kernel:canoe_perf_camera'),
        ('rmnet_perf', '//vendor/qcom/sm8850-modules/qcom/opensource/datarmnet-ext/perf:canoe_perf_perf'),
    }
    actual = [(r.get('module_name'), r.get('target')) for r in contract.get('modules', [])]
    if len(actual) != 2 or set(actual) != expected:
        raise ValueError('R60 scope is exactly camera and repaired rmnet_perf')
    records = contract.get('locked_files', [])
    if not records or not contract.get('modules'):
        raise ValueError('No source inputs or DDK module targets supplied')
    integrated = contract.get('workspace_files', [])
    if not integrated:
        raise ValueError('No expected integrated source hashes supplied')
    integrated_paths = set()
    for row in integrated:
        path = PurePosixPath(row['path'])
        if path.is_absolute() or '..' in path.parts or not re.fullmatch(r'[0-9a-f]{64}', row['sha256']):
            raise ValueError('Invalid integrated source lock')
        integrated_paths.add(row['path'])
    seen = set()
    for row in records:
        path = PurePosixPath(row['path'])
        if path.is_absolute() or '..' in path.parts or row['path'] in seen:
            raise ValueError('Unsafe/duplicate source input')
        seen.add(row['path'])
        local = root / path
        if local.is_symlink() or not local.is_file() or not local.resolve().is_relative_to(root):
            raise ValueError('Missing or redirected source: ' + row['path'])
        if hashlib.sha256(local.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Source SHA256 mismatch: ' + row['path'])
    for row in contract['modules']:
        if not re.fullmatch(r'//[A-Za-z0-9_./+-]+:[A-Za-z0-9_./+-]+', row['target']):
            raise ValueError('Invalid explicit DDK target')
        if not row['output'].startswith('bazel-out/') or not row['output'].endswith('.ko'):
            raise ValueError('Invalid exact module output')
        if not row.get('expected_sources'):
            raise ValueError('No declared source inputs to verify')
        if not set(row['expected_sources']) <= integrated_paths:
            raise ValueError('Source inputs must have integrated SHA256 locks')
        if not re.fullmatch(r'[A-Za-z0-9_]+', row['module_name']) or not row['symvers'].endswith('.symvers'):
            raise ValueError('Invalid expected module identity/symvers output')
    integration = contract.get('integration', {})
    if integration.get('script') not in seen:
        raise ValueError('Integration script must be hash locked')
    return {'schema': 1, 'status': 'PASS', 'locked_files': len(records),
            'targets': [row['target'] for row in contract['modules']],
            'scope': 'Input readiness only; no build or hardware success claimed.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--contract', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.root.resolve(), json.loads(args.contract.read_text())), indent=2))


if __name__ == '__main__':
    main()
