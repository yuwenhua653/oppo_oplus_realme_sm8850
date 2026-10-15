#!/usr/bin/env python3
"""Apply only hash-locked R60 hardware files after the unchanged R13 integration."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

HERE = Path(__file__).resolve().parent


def require(ok, message):
    if not ok:
        raise ValueError(message)


def safe(root, relative):
    p = PurePosixPath(relative)
    require(not p.is_absolute() and '..' not in p.parts, 'Unsafe integration path')
    dest = root / p
    require(not dest.is_symlink() and dest.resolve().is_relative_to(root), 'Redirected integration path')
    return dest


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    root = args.workspace.resolve()
    repo = HERE.parent
    lock = json.loads((HERE / 'hardware-write-lock.json').read_text())
    require(lock['schema'] == 1 and lock['writes'], 'Empty integration lock')
    for rel, pin in lock['git_heads'].items():
        actual = subprocess.check_output(['git', '-C', str(safe(root, rel)), 'rev-parse', 'HEAD'], text=True).strip()
        require(actual == pin, 'Wrong source HEAD: ' + rel)
    plan = []
    seen = set()
    for row in lock['writes']:
        require(row['destination'] not in seen, 'Duplicate destination')
        seen.add(row['destination'])
        data = safe(repo, row['source']).read_bytes()
        require(sha(data) == row['after_sha256'], 'Hardware source/payload hash mismatch')
        dest = safe(root, row['destination'])
        before = sha(dest.read_bytes()) if dest.exists() else None
        require(before in {row['before_sha256'], row['after_sha256']}, 'Unexpected integration preimage: ' + str(dest))
        if args.check:
            require(before == row['after_sha256'], 'Hardware integration has not been applied')
        plan.append((dest, data, row, before))
    if not args.check:
        for dest, data, row, before in plan:
            if before == row['after_sha256']:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            temp = dest.with_name(dest.name + '.r60-tmp')
            with temp.open('xb') as out:
                out.write(data)
            temp.replace(dest)
    result = {'schema': 1, 'status': 'PASS', 'mode': 'check' if args.check else 'apply',
              'writes': [{'destination': row['destination'], 'sha256': row['after_sha256'],
                          'changed': before != row['after_sha256']} for _, _, row, before in plan],
              'hardware_tested': False}
    report = root / 'integration-reports/r60-hardware-integration.json'
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
