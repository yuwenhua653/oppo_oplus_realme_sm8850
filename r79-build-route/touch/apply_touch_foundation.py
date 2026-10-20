#!/usr/bin/env python3
"""Apply the five reviewed Xiaomi-core fixes; this does not enable a module."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent

def sha(data):
    return hashlib.sha256(data).hexdigest()

def safe(root, relative):
    p = PurePosixPath(relative)
    if p.is_absolute() or '..' in p.parts or not p.parts:
        raise ValueError('Unsafe path: ' + relative)
    result = root / p
    cursor = root
    for part in p.parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError('Redirected path: ' + relative)
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError('Escaped path: ' + relative)
    return result

def apply(workspace, verify=False, bundle=ROOT):
    contract = json.loads((bundle / 'touch-write-lock.json').read_text())
    if contract['runtime_enable'] is not False:
        raise ValueError('This source-only patch cannot authorize runtime activation')
    rows = contract['writes']
    if len(rows) != 5 or len({r['destination'] for r in rows}) != 5:
        raise ValueError('Unexpected write inventory')
    pending = []
    for row in rows:
        target = safe(workspace, row['destination'])
        source = safe(bundle, row['source'])
        if not source.is_file() or not target.is_file():
            raise ValueError('Missing source or preimage: ' + row['destination'])
        new, old = source.read_bytes(), target.read_bytes()
        if sha(new) != row['after_sha256'] or len(new) != row['bytes']:
            raise ValueError('Unreviewed payload: ' + row['source'])
        accepted = {row['after_sha256']} if verify else {row['before_sha256'], row['after_sha256']}
        if sha(old) not in accepted:
            raise ValueError('Unexpected preimage: ' + row['destination'])
        pending.append((target, old, new))
    # All hashes and destinations must validate before the first replacement.
    if not verify:
        changed = []
        try:
            for target, old, new in pending:
                if old == new:
                    continue
                temporary = target.with_name(target.name + '.r79-touch-tmp')
                with temporary.open('xb') as stream:
                    stream.write(new)
                temporary.chmod(target.stat().st_mode & 0o777)
                temporary.replace(target)
                changed.append((target, old))
        except Exception:
            for target, old in reversed(changed):
                target.write_bytes(old)
            raise
    return {'status': 'PASS', 'mode': 'check' if verify else 'apply',
            'checked_files': len(pending), 'runtime_enable': False}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    print(json.dumps(apply(args.workspace.resolve(), args.check), indent=2))
