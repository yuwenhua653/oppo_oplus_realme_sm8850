#!/usr/bin/env python3
"""Compile the Myron DT profile from four pinned source projects, without Image/modules."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent
PATHS = ('common', 'vendor/qcom/sm8850', 'vendor/qcom/sm8850-modules', 'vendor/qcom/sm8850-devicetrees')
SPARSE = {
    'common': ['include/dt-bindings', 'include/uapi/linux'],
    'vendor/qcom/sm8850': ['include/dt-bindings', 'include/linux'],
    'vendor/qcom/sm8850-modules': ['qcom/opensource/audio-kernel/include',
        'qcom/opensource/camera-kernel/dt-bindings', 'qcom/opensource/synx-kernel/dt-bindings'],
    'vendor/qcom/sm8850-devicetrees': ['qcom'],
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def run(*args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--entry', required=True, type=Path)
    p.add_argument('--workspace', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--sync', action='store_true')
    p.add_argument('--cpp', default='cpp')
    p.add_argument('--dtc', default='dtc')
    a = p.parse_args()
    profile = json.loads((HERE / 'dt-profile.json').read_text())
    catalog = json.loads((HERE / 'modules.json').read_text())
    require(git(a.entry, 'rev-parse', 'HEAD') == catalog['entry_commit'], 'Unpinned build entry')
    require(not git(a.entry, 'status', '--porcelain', '--untracked-files=normal'), 'Dirty build entry')
    lock = json.loads((a.entry / 'sources.lock.json').read_text())
    projects = {x['path']: x for x in lock['projects'] if x['path'] in PATHS}
    require(set(projects) == set(PATHS), 'Missing locked DT dependency')
    require(projects[PATHS[3]]['commit'] == profile['dts_commit'], 'DTS profile/lock mismatch')
    root = a.workspace.resolve()
    out = a.output.resolve()
    require(root != out and not out.is_relative_to(root), 'Use an output outside source workspace')
    out.mkdir(parents=True, exist_ok=True)
    # Never let a failed attempt leave a manifest claiming current results.
    (out / 'dt-compile.json').unlink(missing_ok=True)
    for name in PATHS:
        spec = projects[name]
        repo = root / name
        if a.sync and not (repo / '.git').exists():
            require(not repo.exists() or not any(repo.iterdir()), 'Non-empty checkout destination: ' + name)
            repo.mkdir(parents=True, exist_ok=True)
            run('git', 'init', repo)
            run('git', '-C', repo, 'remote', 'add', 'origin', spec['url'])
            run('git', '-C', repo, 'sparse-checkout', 'set', *SPARSE[name])
            run('git', '-C', repo, 'fetch', '--depth=1', '--filter=blob:none', 'origin', spec['commit'])
            run('git', '-C', repo, 'checkout', '--detach', 'FETCH_HEAD')
        require(git(repo, 'rev-parse', 'HEAD') == spec['commit'], 'Wrong revision: ' + name)
        require(not git(repo, 'status', '--porcelain', '--untracked-files=normal'), 'Dirty source: ' + name)
    dt = root / PATHS[3]
    modules = root / PATHS[2] / 'qcom/opensource'
    includes = [root / PATHS[1] / 'include', root / 'common/include',
        modules / 'audio-kernel/include', modules / 'camera-kernel', modules / 'synx-kernel', dt / 'qcom']
    names = {b['file'] for b in profile['bases']} | set(profile['board_overlays'])
    names |= {n for b in profile['bases'] for n in b['overlays']}
    result = {'kind': 'host-dtc-only', 'full_kernel_compiled': False, 'device_tested': False,
              'entry_commit': catalog['entry_commit'], 'dts_commit': profile['dts_commit'],
              'source_lock_sha256': sha(a.entry / 'sources.lock.json'), 'sources': projects,
              'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
              'tools': {}, 'files': []}
    for tool in (a.cpp, a.dtc):
        exe = Path(shutil.which(tool) or tool).resolve()
        result['tools'][exe.name] = {'sha256': sha(exe), 'version': subprocess.check_output([str(exe), '--version'], text=True).splitlines()[0]}
    for name in sorted(names):
        inputs = list(dt.rglob(Path(name).stem + '.dts')) + list(dt.rglob(Path(name).stem + '.dtso'))
        require(len(inputs) == 1, 'Ambiguous or missing DTS: ' + name)
        pp = out / (name + '.pp')
        with pp.open('w') as stream:
            run(a.cpp, '-nostdinc', '-undef', '-D__DTS__', '-x', 'assembler-with-cpp',
                *[arg for inc in includes for arg in ('-I', inc)], inputs[0], stdout=stream)
        dest = out / name
        with (out / (name + '.log')).open('w') as log:
            run(a.dtc, '-@', '-I', 'dts', '-O', 'dtb', '-o', dest, pp, stderr=log)
        result['files'].append({'file': name, 'source': str(inputs[0].relative_to(dt)),
            'sha256': sha(dest), 'bytes': dest.stat().st_size})
        print('Compiled ' + name, flush=True)
    result['completed_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    (out / 'dt-compile.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
