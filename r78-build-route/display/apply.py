#!/usr/bin/env python3
"""Verify and apply the exact Myron display source delta; no build/device access."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def child(root, name):
    p = PurePosixPath(name)
    if not name or p.is_absolute() or any(x in ('.', '..') for x in p.parts) or str(p) != name or '\\' in name:
        raise ValueError('non-canonical relative path: ' + str(name))
    return root.joinpath(*p.parts)


def plain(path, missing=False):
    for item in [path, *path.parents]:
        if item.is_symlink():
            raise ValueError('symlink forbidden: ' + str(item))
    if not path.exists():
        if missing:
            return None
        raise ValueError('missing file: ' + str(path))
    if not path.is_file():
        raise ValueError('not a regular file: ' + str(path))
    return path.read_bytes()


def check(package_dir):
    root = Path(package_dir).absolute()
    contract = json.loads(plain(root / 'contract.json'))
    if contract['schema'] != 'myron.r78.display-delta.v1':
        raise ValueError('wrong schema')
    seen = set()
    for row in contract['files']:
        if row['path'] in seen:
            raise ValueError('duplicate package file')
        seen.add(row['path'])
        data = plain(child(root, row['path']))
        if sha(data) != row['sha256'] or len(data) != row['bytes']:
            raise ValueError('package hash mismatch: ' + row['path'])
    destinations = set()
    for row in contract['writes']:
        if row['destination'] in destinations:
            raise ValueError('duplicate destination')
        destinations.add(row['destination'])
        data = plain(child(root / 'payload', row['path']))
        if sha(data) != row['after_sha256'] or len(data) != row['bytes']:
            raise ValueError('bad after image: ' + row['path'])
        if row['before_sha256'] is not None:
            data = plain(child(root / 'preimage', row['path']))
            if sha(data) != row['before_sha256']:
                raise ValueError('bad preimage: ' + row['path'])
        if row.get('r28_sha256'):
            data = plain(child(root / 'r28-effective', row['path']))
            if sha(data) != row['r28_sha256']:
                raise ValueError('bad R28 effective image: ' + row['path'])
    return {'status': 'pass', 'writes': len(destinations), 'contract': contract}


def apply(workspace, package_dir, verify=False):
    root = Path(package_dir).absolute()
    workspace = Path(workspace).absolute()
    contract = check(root)['contract']
    changes = []
    # Every source/preimage check completes before the first replacement.
    for row in contract['writes']:
        path = child(workspace, row['destination'])
        data = plain(path, missing=True)
        digest = None if data is None else sha(data)
        allowed = {row['after_sha256']} if verify else {
            row['before_sha256'], row['after_sha256']}
        if not verify and row.get('r28_sha256'):
            allowed.add(row['r28_sha256'])
        if digest not in allowed:
            raise ValueError('unknown workspace preimage: ' + row['destination'])
        changes.append((row, path, digest))
    written = []
    if not verify:
        for row, path, digest in changes:
            if digest == row['after_sha256']:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            plain(path, missing=True)
            mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
            fd, temp = tempfile.mkstemp(prefix='.r78-display-', dir=path.parent)
            try:
                with os.fdopen(fd, 'wb') as handle:
                    handle.write(plain(child(root / 'payload', row['path'])))
                os.chmod(temp, mode)
                os.replace(temp, path)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
            written.append(row['destination'])
    return {'status': 'pass', 'verified': bool(verify), 'written': written,
            'count': len(changes), 'compiled': False, 'device_actions': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--package-dir', type=Path, default=Path(__file__).parent)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    result = apply(args.workspace, args.package_dir, args.verify) if args.workspace else check(args.package_dir)
    result.pop('contract', None)
    print(json.dumps(result, indent=2))
