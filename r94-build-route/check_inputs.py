#!/usr/bin/env python3
"""Check the complete source-only R94 inventory before sync/build."""
import hashlib
import json
from pathlib import Path, PurePosixPath


def require(ok, message):
    if not ok:
        raise ValueError(message)


def main():
    root = Path(__file__).resolve().parent
    contract = json.loads((root / 'INPUTS.json').read_bytes())
    require(contract['status'] == 'FROZEN_REVIEWED_SOURCE', 'Unfrozen inventory')
    require(contract['baseline_commit'] == 'b193613b3a241430c8c735bdc666ee7bd038993c', 'Wrong R92 baseline')
    require(contract['compile_only'] is True and contract['flashable'] is False, 'Compile-only inventory required')
    rows = contract['files']
    expected = {row['file'] for row in rows}
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.name != 'INPUTS.json'}
    require(len(expected) == len(rows) and expected == actual, 'Source inventory changed')
    for row in rows:
        name = PurePosixPath(row['file'])
        require(not name.is_absolute() and '..' not in name.parts, 'Unsafe source name')
        path = root / name
        require(all(not (root / Path(*name.parts[:i])).is_symlink()
                    for i in range(1, len(name.parts) + 1)), 'Redirected source')
        data = path.read_bytes()
        require(len(data) == row['bytes'], row['file'])
        require(hashlib.sha256(data).hexdigest() == row['sha256'], row['file'])
    print(json.dumps({'status': 'PASS_FROZEN_R94_INPUTS', 'files': len(rows),
                      'compile_only': True, 'flashable': False}))


if __name__ == '__main__':
    main()
