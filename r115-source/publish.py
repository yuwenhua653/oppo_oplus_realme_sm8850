#!/usr/bin/env python3
"""One-time export of the verified R114 source into complete, clean Git trees.

Only this migration uses the historical patch chain. Consumer builds use the
published source commits and never run the migration or apply those patches.
"""
import argparse
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REPOSITORY = 'https://github.com/yuwenhua653/oppo_oplus_realme_sm8850.git'
BRANCHES = {
    'common': 'myron/common-android16-6.12',
    'vendor/qcom/sm8850': 'myron/sm8850',
    'vendor/qcom/sm8850-modules': 'myron/sm8850-modules',
    'vendor/qcom/sm8850-devicetrees': 'myron/sm8850-devicetrees',
}
ENTRY_BRANCH = 'myron/kernel-6.12'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def git(path, *args, env=None, data=None):
    p = subprocess.run(['git', '-C', str(path), *args], input=data,
                       capture_output=True, text=True, env=env)
    if p.returncode:
        raise RuntimeError('git ' + args[0] + ': ' + p.stderr[-4000:])
    return p.stdout.strip()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def compare_snapshot(expected, actual):
    require(len(expected) == len(actual), 'Source project count differs')
    for old, new in zip(expected, actual):
        require(old == new, 'Prepared source differs from tested R114: ' + old['path'])


def snapshot_commit(project, row, branch, reports):
    """Preserve every upstream tracked file, adding only checked R114 paths.

    This is an explicitly documented root snapshot, not a pretend upstream
    history. It avoids publishing truncated ancestry from a shallow clone.
    """
    with tempfile.TemporaryDirectory(prefix='myron-source-index-') as tmp:
        env = {**os.environ, 'GIT_INDEX_FILE': str(Path(tmp) / 'index')}
        git(project, 'read-tree', row['head'], env=env)
        paths = [f['path'] for f in row['files']]
        require(paths and all(not Path(p).is_absolute() and '..' not in Path(p).parts
                              and '.git' not in Path(p).parts for p in paths), 'Unsafe source paths')
        git(project, 'add', '--all', '--', *paths, env=env)
        tree = git(project, 'write-tree', env=env)
    existing = git(project, 'ls-remote', REPOSITORY, 'refs/heads/' + branch)
    if existing:
        sha = existing.split()[0]
        git(project, 'fetch', '--depth=1', '--no-tags', REPOSITORY, sha)
        require(git(project, 'rev-parse', sha + '^{tree}') == tree,
                'Existing public source branch has different content; refusing replacement: ' + branch)
        return sha, tree
    identity = {**os.environ, 'GIT_AUTHOR_NAME': 'myron source integration',
                'GIT_AUTHOR_EMAIL': '41898282+github-actions[bot]@users.noreply.github.com',
                'GIT_COMMITTER_NAME': 'github-actions[bot]',
                'GIT_COMMITTER_EMAIL': '41898282+github-actions[bot]@users.noreply.github.com'}
    message = ('myron: commit complete R114 validated source\n\n'
               'Device: Redmi K90 Pro Max (K90PM / myron)\n'
               'Upstream revision: ' + row['head'] + '\n'
               'Integration baseline: 3b8459064c647ea2a90b5e9d4254736be4dc67ad\n'
               'This root snapshot contains the complete upstream tree plus the\n'
               'byte-checked R114 adaptations. Upstream ancestry is recorded above,\n'
               'not included as a misleading shallow parent. Original licenses retained.\n')
    sha = git(project, 'commit-tree', tree, env=identity, data=message)
    # Create-only lease: never overwrite an existing source branch.
    git(project, 'push', '--force-with-lease=refs/heads/' + branch + ':',
        REPOSITORY, sha + ':refs/heads/' + branch)
    write(reports / (branch.replace('/', '_') + '.json'),
          {'branch': branch, 'commit': sha, 'tree': tree, 'upstream_commit': row['head']})
    return sha, tree


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('repo-root', 'workspace', 'package', 'baseline', 'r18'):
        p.add_argument('--' + n, type=Path, required=True)
    p.add_argument('--jobs', type=int, default=2)
    p.add_argument('--ram-mb', type=int, default=10000)
    a = p.parse_args()
    token = os.environ.get('GH_TOKEN')
    if token:
        # GitHub's short-lived job token is used only for this authorized repo.
        # Keep it out of command arguments, persisted source, and logs.
        os.environ['GIT_CONFIG_COUNT'] = '1'
        os.environ['GIT_CONFIG_KEY_0'] = 'http.https://github.com/.extraheader'
        os.environ['GIT_CONFIG_VALUE_0'] = 'AUTHORIZATION: basic ' + base64.b64encode(
            ('x-access-token:' + token).encode()).decode()
    repo, root = a.repo_root.resolve(), a.workspace.resolve()
    route = repo / 'r115-source'
    reports = root / 'integration-reports/r115-export'
    reports.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(repo / 'r114-build-route'))
    full = load('r115_r114', repo / 'r114-build-route/build_full.py')
    sys.path.insert(0, str(repo / 'r94-build-route'))
    led = full.load('r115_led', repo / 'r94-build-route/build_led.py')
    patch = led.check_patch(repo / 'r94-build-route')
    require(led.pin((repo / 'r92-build-route/build_pd_provider.py').read_bytes())['sha256']
            == led.R92_ENGINE_SHA, 'R92 engine changed')
    sys.path.insert(0, str(repo / 'r92-build-route'))
    parent = full.load('r115_r92', repo / 'r92-build-route/build_pd_provider.py')
    boundary = full.dt_source_bridge.boundary(parent.Boundary, repo)
    boundary.check(repo)
    scope = led.prepare(boundary, a, reports, {})
    full.dt_sandbox.apply(root, reports)
    led.patch_source(root, repo / 'r94-build-route', patch)
    runner = scope['runner']
    for name, args in [
        ('myron-boot-r18/source-fix/apply_soccp.py', ['--soc', str(root / 'vendor/qcom/sm8850')]),
        ('r55-source/dsp-auto-boot/apply_dsp_auto_boot.py', ['--soc', str(root / 'vendor/qcom/sm8850')]),
        ('r81-build-route/apply_wifi.py', ['--workspace', str(root)]),
        ('r82-build-route/apply_cnss.py', ['--workspace', str(root)]),
    ]:
        runner.logged([sys.executable, '-B', str(repo / name), *args], root,
                      reports / (Path(name).stem + '.log'))
    full.runtime_modules.prepare(root, repo, reports)
    lock = json.loads((a.package / 'sources.lock.json').read_text())
    actual = full.source_snapshot(root, lock, reports)
    expected = json.loads((route / 'r114-source-state.json').read_text())
    compare_snapshot(expected, actual)
    write(reports / 'source-equivalence.json', {'match': True, 'projects': len(actual),
          'modified_projects': [r['path'] for r in actual if r['files']]})
    targets = list(dict.fromkeys(runner.build_targets(root, 'full') + scope['contract']['core_targets'] +
                   [r['target'] for r in scope['contract']['validation_only_modules']] +
                   [led.MODULE['target'], full.runtime_modules.TARGET]))
    require(targets == json.loads((route / 'checkout/targets.json').read_text()), 'Target list differs')
    require({r['path'] for r in actual if r['files']} == set(BRANCHES), 'Unexpected modified project')
    public_lock = copy.deepcopy(lock)
    public_lock.update(profile='myron-r115-clean-source', purpose='Full committed Redmi K90PM kernel source')
    public_lock['provenance']['r114_integration_commit'] = '3b8459064c647ea2a90b5e9d4254736be4dc67ad'
    bypath = {r['path']: r for r in actual}
    for project in public_lock['projects']:
        if project['path'] not in BRANCHES:
            continue
        branch = BRANCHES[project['path']]
        sha, tree = snapshot_commit(root / project['path'], bypath[project['path']], branch, reports)
        project['upstream'] = {'url': project['url'], 'commit': project['commit']}
        project.update(url=REPOSITORY, commit=sha, branch=branch, tree=tree)
    # Explicit, Git-tracked public build inputs only; no logs, runtime images,
    # local SELinux/Recovery assembly, or historical private input archives.
    output = repo.parent / 'myron-source-entry'
    require(not output.exists(), 'Fresh source entry output required')
    output.mkdir()
    entries = git(repo, 'ls-files', 'r115-source/checkout').splitlines()
    require(entries, 'Consumer build inputs must be committed before publishing')
    for name in entries:
        src = repo / name
        dst = output / src.relative_to(route / 'checkout')
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    write(output / 'sources.lock.json', public_lock)
    metadata = root / 'myron_artifact_metadata/BUILD.bazel'
    shutil.copy2(metadata, output / 'metadata.BUILD.bazel')
    write(output / 'source-provenance.json', {'r114_run': 41252685590,
          'r114_source_equivalence': True, 'changed_projects': [r for r in actual if r['files']],
          'history': 'Complete root snapshots; upstream commits recorded in sources.lock.json.'})
    git(output, 'init', '--quiet')
    git(output, 'config', 'user.name', 'github-actions[bot]')
    git(output, 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com')
    git(output, 'add', '--all')
    tree = git(output, 'write-tree')
    existing = git(output, 'ls-remote', REPOSITORY, 'refs/heads/' + ENTRY_BRANCH)
    parents = []
    if existing:
        old = existing.split()[0]
        git(output, 'fetch', '--depth=1', '--no-tags', REPOSITORY, old)
        parents = ['-p', old]
        lease = old
    else:
        lease = ''
    sha = git(output, 'commit-tree', tree, *parents,
              data='myron: build directly from committed R114 kernel sources\n')
    git(output, 'push', '--force-with-lease=refs/heads/' + ENTRY_BRANCH + ':' + lease,
        REPOSITORY, sha + ':refs/heads/' + ENTRY_BRANCH)
    record = {'entry_branch': ENTRY_BRANCH, 'entry_commit': sha,
              'source_projects': [p for p in public_lock['projects'] if p['path'] in BRANCHES]}
    write(reports / 'published.json', record)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            f.write('entry_commit=' + sha + '\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
