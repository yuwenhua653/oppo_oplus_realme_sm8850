#!/usr/bin/env python3
"""Apply seven exact, compile-only postimages after the frozen R61 preparation."""
import argparse
import json
from pathlib import Path
import subprocess
from check_charge_inputs import check_overlay, overlay_bytes, require, safe, sha


def plan(workspace, repo, contract, verify=False):
    check_overlay(repo, contract)
    for relative, expected in contract['git_heads'].items():
        source = safe(workspace, relative, exists=False)
        actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
        require(actual == expected, 'Source/toolchain HEAD mismatch: ' + relative)
    pending = []
    for row in contract['writes']:
        target = safe(workspace, row['destination'], exists=False)
        require(not target.exists() or target.is_file(), 'Non-file destination')
        actual = sha(target.read_bytes()) if target.exists() else None
        require(actual in {row['before_sha256'], row['after_sha256']},
                'Unexpected preimage: ' + row['destination'])
        require(not verify or actual == row['after_sha256'], 'Overlay not applied: ' + row['destination'])
        pending.append((target, overlay_bytes(repo, row), actual != row['after_sha256']))
    return pending


def apply(workspace, repo, contract, verify=False):
    pending = plan(workspace, repo, contract, verify)
    # Plan every write before any mutation. A bad late preimage changes nothing.
    if not verify:
        for target, data, changed in pending:
            if changed:
                target.parent.mkdir(parents=True, exist_ok=True)
                temp = target.with_name(target.name + '.r75-tmp')
                with temp.open('xb') as stream:
                    stream.write(data)
                temp.replace(target)
    return {'schema': 1, 'status': 'PASS', 'compile_only': True, 'mode': 'verify' if verify else 'apply',
            'writes': [{'path': str(p.relative_to(workspace)), 'sha256': sha(data), 'changed': changed}
                       for p, data, changed in pending]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', required=True, type=Path)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    repo, workspace = args.repo_root.resolve(), args.workspace.resolve()
    print(json.dumps(apply(workspace, repo, json.loads((repo / 'r75-build-route/charge-contract.json').read_text()), args.check), indent=2))
