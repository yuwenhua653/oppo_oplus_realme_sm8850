#!/usr/bin/env python3
"""Extract only the three hash-pinned R18/R13 source packages; no network."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile

ARCHIVES = [
    ('myron-boot-r18.zip', 'a3c7e97e4a28f6574a619bcc10dab8962911ed5fcef8617aeb7fc835bdbe7d13', 'myron-boot-r18', 14),
    ('myron-boot-r18/baseline/myron-qcom-platform-r1.zip', '770dd907a0d51984a5d005285daef648859f6f7db68576cf98ec823d41b52ca2', 'myron-qcom-platform-r1', 67),
    ('myron-boot-r18/baseline/myron-adaptation-r12.zip', '64dbec4a01124317682f28e0fce61bd885247af1e05b5cac5e4990ad838111c1', 'myron-adaptation-r12', 988),
]


def require(value, message):
    if not value:
        raise ValueError(message)


def extract(root, name, expected, prefix, count):
    archive = root / name
    require(archive.is_file() and not archive.is_symlink(), 'Missing or redirected archive: ' + name)
    require(hashlib.sha256(archive.read_bytes()).hexdigest() == expected, 'Archive SHA256 mismatch: ' + name)
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        require(len({x.filename for x in entries}) == len(entries), 'Duplicate ZIP entries')
        selected = []
        for item in entries:
            path = PurePosixPath(item.filename)
            require(not path.is_absolute() and '..' not in path.parts and not item.is_dir(), 'Unsafe ZIP entry')
            require(stat.S_IFMT(item.external_attr >> 16) in (0, stat.S_IFREG), 'Nonregular ZIP entry')
            if path.parts[0] != prefix:
                require(prefix == 'myron-qcom-platform-r1' and item.filename == '.github/workflows/build-myron-qcom-platform.yml', 'Unexpected ZIP prefix')
                continue  # Never replace an existing repository workflow.
            selected.append(item)
        require(len(selected) == count, 'Unexpected source package file count')
        pending = []
        allowed = {root / x.filename for x in selected}
        for existing in (root / prefix).rglob('*') if (root / prefix).exists() else []:
            require(not existing.is_symlink(), 'Redirected existing package path')
            require(existing.is_dir() or existing in allowed, 'Unexpected existing package file')
        for item in selected:
            target = root / item.filename
            data = bundle.read(item)
            require(not target.is_symlink(), 'Redirected output')
            require(not target.exists() or target.read_bytes() == data, 'Conflicting existing source file')
            pending.append((target, data))
        for target, data in pending:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return {'archive': name, 'sha256': expected, 'extracted_files': count, 'prefix': prefix}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    rows = [extract(root, *row) for row in ARCHIVES]
    destination = root / 'kernel_workspace/myron-platform-r1/integration-reports/r55-source-packages.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({'schema': 1, 'status': 'PASS', 'archives': rows}, indent=2) + '\n')
    print('Verified and extracted R18 source bundle, platform package and R13 adaptation inputs.')


if __name__ == '__main__':
    main()
