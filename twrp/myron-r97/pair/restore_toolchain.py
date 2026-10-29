#!/usr/bin/env python3
"""Restore the exact R96 GCC 13 cross toolchain; no package installation."""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.parse
import urllib.request

def require(v, message):
    if not v:
        raise ValueError(message)

def pinned(path, row):
    if not path.is_file() or path.stat().st_size != row['bytes']:
        return False
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(data)
    return h.hexdigest() == row['sha256']

def restore(manifest, destination):
    manifest = Path(manifest).resolve()
    destination = Path(destination).resolve()
    data = json.loads(manifest.read_text())
    cache = destination / 'debs'
    sysroot = destination / 'sysroot'
    cache.mkdir(parents=True, exist_ok=True)
    sysroot.mkdir(parents=True, exist_ok=True)
    names = [Path(row['path']).name for row in data['packages']]
    require(len(names) == len(set(names)), 'duplicate package names')

    def obtain(row):
        name = Path(row['path']).name
        target = cache / name
        if pinned(target, row):
            return target, 'verified cache'
        errors = []
        for url in dict.fromkeys([row['actual_download_url'], row['download_url']]):
            parsed = urllib.parse.urlparse(url)
            require(parsed.scheme == 'https' and parsed.hostname in {'archive.ubuntu.com', 'snapshot.ubuntu.com'}, 'unexpected package host')
            require(Path(parsed.path).name == name, 'package URL filename mismatch')
            temp = cache / (name + '.partial')
            try:
                with urllib.request.urlopen(url, timeout=45) as response, temp.open('wb') as output:
                    total = 0
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        total += len(block)
                        require(total <= row['bytes'], 'oversized package response')
                        output.write(block)
                require(pinned(temp, row), 'package pin mismatch: ' + name)
                os.replace(temp, target)
                return target, url
            except Exception as exc:
                temp.unlink(missing_ok=True)
                errors.append(str(exc))
        raise RuntimeError(name + ': ' + '; '.join(errors))

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(obtain, row) for row in data['packages']]
        acquired = []
        for i, future in enumerate(futures, 1):
            path, route = future.result()
            acquired.append((path, route))
            print(f'{i}/{len(futures)} verified {path.name}', flush=True)
    # Keep unpack order identical to the recorded input manifest.
    for path, _ in acquired:
        subprocess.run(['dpkg-deb', '--extract', str(path), str(sysroot)], check=True)
    original_root = next(arg.split('=', 1)[1] for arg in data['compile_argv'] if arg.startswith('--sysroot='))
    relocate = lambda text: text.replace(original_root, str(sysroot))
    result = {
        'manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
        'compile_argv': [relocate(x) for x in data['compile_argv']],
        'strip_argv': [relocate(x) for x in data['strip_argv']],
        'env_overrides': {k: relocate(v) for k, v in data['env_overrides'].items()},
        'sysroot': str(sysroot),
        'packages': [{**row, 'recovered_path': str(item[0]), 'recovery_route': item[1]}
                     for row, item in zip(data['packages'], acquired)],
    }
    env = {**os.environ, **result['env_overrides']}
    probe = subprocess.run([result['compile_argv'][0], '--version'], env=env, check=True, capture_output=True, text=True)
    result['compiler_version'] = probe.stdout.splitlines()[0]
    (destination / 'restored-toolchain.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ['compile_argv', 'strip_argv', 'env_overrides', 'compiler_version']}, indent=2))
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--destination', required=True)
    args = parser.parse_args()
    restore(args.manifest, args.destination)
