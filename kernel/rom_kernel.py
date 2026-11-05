#!/usr/bin/env python3
"""Device-owned Kleaf adapter. Does not patch the ROM or accept prebuilt kernels."""
import argparse
import collections
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()


def entry_check(entry, catalog):
    require(git(entry, 'rev-parse', 'HEAD') == catalog['entry_commit'], 'Build entry revision differs from modules.json')
    require(not git(entry, 'status', '--porcelain', '--untracked-files=normal'), 'Build entry has uncommitted changes')


def safe_file(root, relative):
    p = Path(relative)
    require(not p.is_absolute() and '..' not in p.parts, 'Unsafe artifact path')
    result = root / p
    require(result.is_file() and not result.is_symlink(), 'Missing/redirected output: ' + relative)
    require(result.resolve().is_relative_to(root.resolve()), 'Escaping output path')
    return result


def make_text(catalog):
    lines = ['# Generated from modules.json. Regenerate with kernel/rom_kernel.py emit-make.']
    for group, names in catalog['groups'].items():
        lines.append('MYRON_' + group.upper() + '_MODULES := ' + ' '.join(catalog['modules'][n]['file'] for n in names))
    lines.append('MYRON_ALL_MODULES := ' + ' '.join(sorted(r['file'] for r in catalog['modules'].values())))
    return '\n'.join(lines) + '\n'


def validate_catalog(catalog):
    require((HERE / 'modules.mk').read_text() == make_text(catalog), 'modules.mk is stale; run emit-make')
    modules = catalog['modules']
    require(len({r['file'] for r in modules.values()}) == len(modules), 'Duplicate module filename')
    for row in modules.values():
        require(Path(row['file']).name == row['file'] and row['file'].endswith('.ko'), 'Invalid module filename')
    groups = catalog['groups']
    require(set(groups['system']).isdisjoint(groups['vendor']), 'Duplicate system/vendor providers')
    require(set(groups['system'] + groups['vendor']) == set(modules), 'Incomplete install set')
    for group in ('ramdisk', 'boot_load', 'recovery_load'):
        names = groups[group]
        require(len(names) == len(set(names)), 'Repeated load entry')
        for n in names:
            require(set(modules[n]['depends']) <= set(names), 'Missing dependency in ' + group + ': ' + n)
    require(set(groups['boot_load'] + groups['recovery_load']) <= set(groups['ramdisk']), 'Load list exceeds ramdisk')


def stage(full, dist, entry, catalog):
    """Validate fresh compiler results, then expose explicit Android build outputs."""
    status = read(full / 'validation-status.json')
    require(status['verified'] is True, 'Kernel build did not pass validation')
    manifest = read(full / 'artifact-manifest.json')
    release = manifest['kernel_release']
    require(release == status['kernel_release'], 'Release mismatch')
    require(not any(s in release for s in ('dirty', 'maybe', 'mybe')), 'Dirty/placeholder kernel release')
    records = {r['file']: r for r in manifest['files']}
    # All collected files are checked, including symbol tables used below.
    for name, row in records.items():
        p = safe_file(full, name)
        require(p.stat().st_size == row['bytes'] and sha(p) == row['sha256'], 'Artifact hash mismatch: ' + name)
    parser = load('myron_elf', entry / 'elf_parser.py').parse_elf
    selected = {}
    for name, row in catalog['modules'].items():
        require(row['source'] in records, 'Missing source-built module: ' + name)
        path = safe_file(full, row['source'])
        parsed = parser(path.read_bytes())
        require(parsed['name'] == name, 'Module identity mismatch')
        require(parsed['info']['vermagic'][0].split()[0] == release, 'Module vermagic mismatch: ' + name)
        require(parsed['depends'] == row['depends'], 'Dependency graph changed; review module catalog: ' + name)
        selected[name] = parsed
    symvers = [safe_file(full, p) for p in records if p.endswith('/common/kernel_aarch64/vmlinux.symvers')]
    require(len(symvers) == 1, 'Missing/ambiguous vmlinux symbol table')
    providers = collections.defaultdict(list)
    for line in symvers[0].read_text().splitlines():
        fields = line.split()
        providers[fields[1]].append(('vmlinux', int(fields[0], 16)))
    for name, parsed in selected.items():
        for symbol, crc in parsed['export_crcs'].items():
            providers[symbol].append((name, crc))
    checks = 0
    for name, parsed in selected.items():
        for symbol, crc in parsed['versions'].items():
            options = providers[symbol]
            require(len(options) == 1 and options[0][1] == crc, 'Missing/conflicting ABI provider: ' + name + ':' + symbol)
            checks += 1
    images = [safe_file(full, p) for p in records if p.endswith('/common/kernel_aarch64/Image')]
    require(len(images) == 1, 'Missing/ambiguous Image')
    require(manifest['linux_banner'].encode() in images[0].read_bytes(), 'Image banner mismatch')
    dist.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.myron-stage-', dir=dist.parent) as tmp:
        temp = Path(tmp)
        (temp / 'modules').mkdir()
        shutil.copyfile(images[0], temp / 'Image')
        for row in catalog['modules'].values():
            shutil.copyfile(safe_file(full, row['source']), temp / 'modules' / row['file'])
        report = {'kernel_release': release, 'linux_banner': manifest['linux_banner'],
                  'installed_module_names': len(selected), 'import_crc_checks': checks,
                  'groups': {k: len(v) for k, v in catalog['groups'].items()},
                  'device_tested': False, 'full_rom_compiled': False,
                  'files': {str(p.relative_to(temp)): sha(p) for p in sorted(temp.rglob('*')) if p.is_file()}}
        write(temp / 'stage-report.json', report)
        if dist.exists():
            require(not dist.is_symlink(), 'Refusing redirected staging directory')
            shutil.rmtree(dist)
        shutil.copytree(temp, dist)
    return report


def fingerprint(entry, catalog):
    inputs = {str(p.relative_to(HERE)): sha(p) for p in HERE.iterdir() if p.suffix in ('.py', '.json', '.mk')}
    return {'adapter': inputs, 'entry': catalog['entry_commit'], 'source_lock': sha(entry / 'sources.lock.json')}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'build', 'verify', 'emit-make'])
    p.add_argument('--entry', type=Path, default=Path('kernel/xiaomi/myron-build'))
    p.add_argument('--workspace', type=Path, default=Path('out/target/product/myron/obj/MYRON_KERNEL/workspace'))
    p.add_argument('--dist', type=Path, default=Path('out/target/product/myron/obj/MYRON_KERNEL/dist'))
    p.add_argument('--jobs', type=int, default=2)
    p.add_argument('--ram-mb', type=int, default=10000)
    a = p.parse_args()
    catalog = read(HERE / 'modules.json')
    if a.action == 'emit-make':
        (HERE / 'modules.mk').write_text(make_text(catalog))
        return
    validate_catalog(catalog)
    entry, workspace, dist = a.entry.resolve(), a.workspace.resolve(), a.dist.resolve()
    require(a.jobs >= 1 and a.ram_mb >= 2048, 'Invalid resource limits')
    entry_check(entry, catalog)
    # Keep nested repositories outside Soong's source discovery and protect concurrent m invocations.
    workspace.parent.mkdir(parents=True, exist_ok=True)
    with (workspace.parent / 'adapter.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if a.action == 'prepare':
            subprocess.run([sys.executable, '-B', str(entry / 'sync_sources.py'), '--workspace', str(workspace), '--jobs', str(min(a.jobs, 16))], check=True)
        sys.path.insert(0, str(entry))
        builder = load('myron_source_build', entry / 'build.py')
        source_lock = read(entry / 'sources.lock.json')
        builder.validate_source_lock(source_lock)
        require((workspace / 'common/.git').exists(), 'Run python3 device/xiaomi/myron/kernel/rom_kernel.py prepare first (use the same --workspace when OUT_DIR differs).')
        source_state = builder.check_sources(workspace, source_lock)
        if a.action == 'prepare':
            print('Pinned sources ready. Use the normal ROM lunch and m commands; kernel compilation is a build dependency.')
            return
        if a.action == 'verify':
            print('Source revisions and module graph verified.')
            return
        key = fingerprint(entry, catalog)
        cache = dist / 'build-key.json'
        if cache.is_file() and read(cache) == key:
            report = read(dist / 'stage-report.json')
            for name, digest in report['files'].items():
                require(sha(safe_file(dist, name)) == digest, 'Cached kernel/module changed; remove only MYRON_KERNEL/dist and rebuild')
            print('Reusing verified source-built kernel: ' + report['kernel_release'])
            return
        full = workspace / 'integration-artifacts/full'
        raw_status = workspace / 'integration-reports/build-status.json'
        if full.is_dir() and raw_status.is_file():
            previous = read(raw_status)
            if (previous.get('success') is True and previous.get('entry_commit') == catalog['entry_commit']
                    and previous.get('sources') == source_state):
                # A device packaging/DT-rule edit must not spend another full
                # kernel build. Revalidate compiler outputs before restaging.
                stage(full, dist, entry, catalog)
                write(cache, key)
                print('Revalidated existing source build; updated device staging only.')
                return
        if full.exists():
            require(not full.is_symlink(), 'Refusing redirected compiler output')
            shutil.rmtree(full)
        subprocess.run([sys.executable, '-B', str(entry / 'build.py'), '--workspace', str(workspace), '--no-sync', '--jobs', str(a.jobs), '--ram-mb', str(a.ram_mb)], check=True)
        require(read(workspace / 'integration-reports/build-status.json')['success'], 'Source build failed')
        stage(full, dist, entry, catalog)
        write(cache, key)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        sys.exit('myron kernel: ' + str(error))
