#!/usr/bin/env python3
"""Apply the reviewed R61 compile-only layer after unchanged R13 validation."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

HERE = Path(__file__).resolve().parent


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe(root, relative):
    p = PurePosixPath(relative)
    require(relative and not p.is_absolute() and '..' not in p.parts, 'Unsafe path: ' + relative)
    out = root / p
    require(not out.is_symlink() and out.resolve().is_relative_to(root), 'Redirected path: ' + relative)
    return out


def plan(root, repo, lock, check=False):
    require(lock.get('schema') == 1 and lock.get('writes'), 'Empty integration lock')
    for relative, pin in lock['git_heads'].items():
        actual = subprocess.check_output(['git', '-C', str(safe(root, relative)), 'rev-parse', 'HEAD'], text=True).strip()
        require(actual == pin, 'Wrong source HEAD: ' + relative)
    for row in lock.get('upstream_files', []):
        require(row['repo'] in lock['git_heads'], 'Unlocked upstream repository')
        repo_root = safe(root, row['repo'])
        path = safe(repo_root, row['path'])
        original = subprocess.check_output(['git', '-C', str(repo_root), 'show', 'HEAD:' + row['path']])
        require(path.read_bytes() == original, 'Upstream source differs from pinned Git tree: ' + row['path'])
        require(sha(original) == row['sha256'], 'Upstream Git blob differs from reviewed SHA256')
    result, seen = [], set()
    for row in lock['writes']:
        dest = safe(root, row['destination'])
        require(row['destination'] not in seen, 'Duplicate integration destination')
        seen.add(row['destination'])
        data = safe(repo, row['source']).read_bytes()
        require(sha(data) == row['after_sha256'], 'Source/payload SHA mismatch: ' + row['source'])
        original = dest.read_bytes() if dest.exists() else None
        before = sha(original) if original is not None else None
        require(before in {row['before_sha256'], row['after_sha256']},
                'Unexpected preimage: ' + row['destination'] + '; actual_sha256=' + str(before) +
                '; actual_bytes=' + str(len(original) if original is not None else None) +
                '; expected_before=' + str(row['before_sha256']) + '; expected_after=' + row['after_sha256'])
        if check:
            require(before == row['after_sha256'], 'Integration not applied: ' + row['destination'])
        result.append((dest, data, row, before))
    return result


def apply(root, repo, lock, check=False):
    # Every payload, Git revision and preimage is validated before ANY source write.
    planned = plan(root, repo, lock, check)
    if not check:
        for dest, data, row, before in planned:
            if before == row['after_sha256']:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            temp = dest.with_name(dest.name + '.r61-tmp')
            with temp.open('xb') as stream:
                stream.write(data)
            temp.replace(dest)
    return {'schema': 1, 'status': 'PASS', 'mode': 'check' if check else 'apply',
            'compile_only': True, 'hardware_tested': False,
            'upstream_files': [{'repo': row['repo'], 'path': row['path'],
                                'git_head': lock['git_heads'][row['repo']],
                                'sha256': sha(safe(root, row['repo'] + '/' + row['path']).read_bytes())}
                               for row in lock.get('upstream_files', [])],
            'writes': [{'destination': row['destination'], 'sha256': row['after_sha256'],
                        'changed': before != row['after_sha256']} for _, _, row, before in planned]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    root = args.workspace.resolve()
    report = root / 'integration-reports/r61-battery-integration.json'
    report.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = apply(root, HERE.parent, json.loads((HERE / 'battery-write-lock.json').read_text()), args.check)
    except Exception as error:
        result = {'schema': 1, 'status': 'FAIL', 'error': str(error), 'compile_only': True}
        report.write_text(json.dumps(result, indent=2) + '\n')
        raise
    report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
