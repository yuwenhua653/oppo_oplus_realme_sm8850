#!/usr/bin/env python3
"""Explicit migration from the unavailable R13 DTS commit to a pinned candidate.

Archives and historical reports stay unchanged. Only extracted revision guards
and the derived bundle manifest change. This is not a whole-tree equivalence claim.
"""
import argparse
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

OLD = '8b86fedda64183338411f9751f5e62ce25997620'
NEW = '928b59fcca6306aaba39343a474dc5930d8f424d'
TREE = '3da2d6f5050abf14d97ab7503d7c94cf8188288c'
DT = 'vendor/qcom/sm8850-devicetrees'
R18_SHA = 'a3c7e97e4a28f6574a619bcc10dab8962911ed5fcef8617aeb7fc835bdbe7d13'
R13_SHA = '64dbec4a01124317682f28e0fce61bd885247af1e05b5cac5e4990ad838111c1'
PLATFORM_SHA = '770dd907a0d51984a5d005285daef648859f6f7db68576cf98ec823d41b52ca2'
OLD_LOCK = 'ef3d806f679ac8e0bf1371e6ab6dfc173118a32e3a66f44f684116bc0b52e756'
DT_MANIFEST = 'myron-qcom-platform-r1/devicetrees/myron-dt-patch-manifest.json'

def require(ok, message):
    if not ok:
        raise ValueError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def encoded(obj):
    return (json.dumps(obj, indent=2) + '\n').encode()

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def originals(repo):
    raw = (repo / 'myron-boot-r18.zip').read_bytes()
    require(sha(raw) == R18_SHA, 'R18 archive changed')
    result = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as outer:
        for name, expected in [('myron-qcom-platform-r1', PLATFORM_SHA),
                               ('myron-adaptation-r12', R13_SHA)]:
            data = outer.read('myron-boot-r18/baseline/' + name + '.zip')
            require(sha(data) == expected, 'Nested archive changed: ' + name)
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                result.update({n: archive.read(n) for n in archive.namelist() if n.startswith(name + '/')})
    return result

def expected_edits(repo):
    original = originals(repo)
    edits = {}
    p = 'myron-qcom-platform-r1/sources.lock.json'
    require(sha(original[p]) == OLD_LOCK, 'Original source lock changed')
    lock = json.loads(original[p])
    projects = [x for x in lock['projects'] if x['path'] == DT]
    require(len(projects) == 1 and projects[0]['commit'] == OLD, 'Unexpected old DTS project')
    projects[0]['commit'] = NEW
    edits[p] = encoded(lock)
    for p in ['myron-qcom-platform-r1/devicetrees/myron-dt-patch-manifest.json',
              'myron-adaptation-r12/dt/dt-manifest.json']:
        obj = json.loads(original[p])
        require(obj['revision'] == OLD, 'Unexpected original DTS guard')
        obj['revision'] = NEW
        edits[p] = encoded(obj)
    p = 'myron-adaptation-r12/dt/validate_dt.py'
    anchor = ('DT_REVISION = "' + OLD + '"').encode()
    require(original[p].count(anchor) == 1, 'Ambiguous validator revision guard')
    edits[p] = original[p].replace(anchor, ('DT_REVISION = "' + NEW + '"').encode())
    p = 'myron-adaptation-r12/bundle-lock.json'
    bundle = json.loads(original[p])
    for item in bundle['files']:
        key = 'myron-adaptation-r12/' + item['path']
        if key in edits:
            require(item['sha256'] == sha(original[key]), 'Original bundle entry mismatch')
            item['sha256'] = sha(edits[key])
    edits[p] = encoded(bundle)
    return original, edits

def collection_manifest(data):
    # Exact changes made by the original hotfix_02, in addition to the revision.
    for before, after in [
        ('c0934e8cfc229561fa62f7844f6e2cb5e6415ffe261916bb566f0ac75ab5af74',
         '1eb047983a06ecfae3c88ef06c3ae9f7fd336fc214fc5f8b057e7fba2c2e1571'),
        ('6b107daabc1a5a652d131063ce81cd6fb5a9495760f2c80c3ed1db545e8df2da',
         '33a50ccf84bfeb9bb5387322be4c866dda238a9bb58cf4efefdd9e0f088dd357')]:
        require(data.count(before.encode()) == 1, 'Ambiguous collection manifest anchor')
        data = data.replace(before.encode(), after.encode())
    return data

def migrate(repo, verify=False):
    original, edits = expected_edits(repo)
    for name, data in edits.items():
        path = repo / name
        require(path.is_file() and not path.is_symlink(), 'Missing extracted input: ' + name)
        allowed = (data,) if verify else (original[name], data)
        if name == DT_MANIFEST:
            allowed += (collection_manifest(data),)
        require(path.read_bytes() in allowed, 'Unreviewed input change: ' + name)
    if not verify:
        for name, data in edits.items():
            if (repo / name).read_bytes() == original[name]:
                (repo / name).write_bytes(data)
    return sha(edits['myron-qcom-platform-r1/sources.lock.json'])

def normalize(workspace, repo):
    dt = workspace / DT
    def git(*args):
        return subprocess.check_output(['git', '-C', str(dt), *args])
    require(git('rev-parse', 'HEAD').decode().strip() == NEW, 'Wrong DTS candidate HEAD')
    require(git('rev-parse', 'HEAD^{tree}').decode().strip() == TREE, 'Wrong DTS candidate tree')
    require(not git('status', '--porcelain').strip(), 'DTS preflight requires a clean checkout')
    original = originals(repo)
    manifest = json.loads(original['myron-qcom-platform-r1/devicetrees/myron-dt-patch-manifest.json'])
    pending = {}
    for path in ('BUILD.bazel', 'qcom/Makefile', 'qcom/camera/config/canoe.mk'):
        s = (dt / path).read_text()
        if path == 'BUILD.bazel':
            replacements = [('            "qcom/wlan/Kbuild",\n',
                             '            "qcom/wlan/Kbuild",\n            "qcom/fingerprint/Kbuild",\n')]
        elif path == 'qcom/Makefile':
            replacements = [('\t\talor-interposer-qrd-st54l-pandeiro-overlay.dtbo \\\n\t\tmyron-sm8850-overlay.dtbo',
                             '\t\talor-interposer-qrd-st54l-pandeiro-overlay.dtbo'),
                            ('\n-include $(src)/dtbo_rules.mk\n', '')]
        else:
            replacements = [('\talor-camera-sensor-rcm-peach.dtbo \\\n\tmyron-sm8850-camera-sensor.dtbo',
                             '\talor-camera-sensor-rcm-peach.dtbo')]
        for before, after in replacements:
            require(s.count(before) == 1, 'Normalization anchor changed: ' + path)
            s = s.replace(before, after, 1)
        pending[path] = s.encode()
    # Every affected preimage must be exactly the archived old input.
    for row in manifest['files']:
        data = pending.get(row['path'], (dt / row['path']).read_bytes())
        require(sha(data) == row['before_sha256'], 'Historical DTS preimage mismatch: ' + row['path'])
    retention = json.loads(original['myron-adaptation-r12/retention/retention-lock.json'])
    validation = json.loads(original['myron-adaptation-r12/dt/local-validation.json'])
    records = [(x['source'], x['source_git_blob']) for x in retention['outputs'] + retention['excluded_unobserved_outputs']]
    records += [(x['path'], x['git_blob']) for x in validation['source_provenance'] if 'devicetrees' in x['repository']]
    for path, expected in records:
        data = pending.get(path, (dt / path).read_bytes())
        blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        require(blob == expected, 'Historical DTS blob mismatch: ' + path)
    for path, data in pending.items():
        (dt / path).write_bytes(data)
    report = {'old_revision': OLD, 'new_revision': NEW, 'new_tree': TREE,
              'normalizations': {p: sha(b) for p, b in pending.items()},
              'historical_hash_checks': len(manifest['files']) + len(records),
              'whole_old_tree_equivalence': False, 'hardware_tested': False,
              'notes': 'Old myron board/charger/touch/camera/display source hashes are incomplete. Preserve OEM DT images during later package assembly.'}
    reports = workspace / 'integration-reports'
    reports.mkdir(parents=True, exist_ok=True)
    (reports / 'r114-dt-migration.json').write_bytes(encoded(report))
    print(json.dumps(report, indent=2))

def legacy(repo, workspace):
    migrate(repo, verify=True)
    _, edits = expected_edits(repo)
    ci = repo / 'r55-source/ci'
    lock = json.loads((ci / 'legacy-preparation-lock.json').read_bytes())
    for row in lock['steps']:
        require(sha((ci / row['file']).read_bytes()) == row['sha256'], 'Legacy helper changed')
    env = dict(os.environ, WORKSPACE_DIR=str(workspace), PACKAGE_DIR=str(repo / 'myron-qcom-platform-r1'))
    for row in lock['steps']:
        data = (ci / row['file']).read_bytes()
        if row['file'] == 'hotfix_01_qpace.sh':
            anchor = ('expected_head = "' + OLD + '"').encode()
            require(data.count(anchor) == 1, 'Ambiguous QPACE revision guard')
            data = data.replace(anchor, ('expected_head = "' + NEW + '"').encode())
        elif row['file'] == 'hotfix_02_dt_collection.sh':
            for old, new in [
                ('50abdcf04f749015f2d9cb5324b40b5cff8fb145966e53dd651869c243bc7870', sha(edits[DT_MANIFEST])),
                ('f41f9badbdf915563ac6c9c8a9fc6930015a77dad9e1822e4e207cd6e94c6191', sha(collection_manifest(edits[DT_MANIFEST])))]:
                require(data.count(old.encode()) == 1, 'Ambiguous collection helper checksum')
                data = data.replace(old.encode(), new.encode())
        # No modification to frozen repository helpers or their lock records.
        subprocess.run(['bash'], input=data, env=env, check=True)
    subprocess.run([sys.executable, str(repo / 'myron-adaptation-r12/install_hooks.py'),
                    '--package', str(repo / 'myron-qcom-platform-r1'), '--workspace', str(workspace)], check=True)

def sync(repo, workspace, jobs):
    digest = migrate(repo, verify=True)
    module = load('r114_locked_retry', repo / 'r61-build-route/sync_with_retry.py')
    require(module.LOCK_SHA256 == OLD_LOCK, 'Original retry contract changed')
    module.LOCK_SHA256 = digest
    return module.execute(repo / 'myron-qcom-platform-r1', workspace, jobs)

def boundary(parent_class, repo):
    class MigratedBoundary(parent_class):
        def check(self, path):
            original, *rest = super().check(path)
            require(original['sources_lock_sha256'] == OLD_LOCK, 'Unexpected inherited source contract')
            current = copy.deepcopy(original)
            current['sources_lock_sha256'] = migrate(Path(path).resolve(), verify=True)
            return (current, *rest)
    return MigratedBoundary(repo)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=['migrate', 'verify', 'normalize', 'legacy', 'sync'])
    ap.add_argument('--repo', type=Path, required=True)
    ap.add_argument('--workspace', type=Path)
    ap.add_argument('--jobs', type=int, default=4)
    a = ap.parse_args()
    repo = a.repo.resolve()
    if a.action in ('migrate', 'verify'):
        print('Migrated source lock:', migrate(repo, a.action == 'verify'))
    else:
        require(a.workspace is not None, 'Workspace required')
        root = a.workspace.resolve()
        if a.action == 'normalize': normalize(root, repo)
        elif a.action == 'legacy': legacy(repo, root)
        else: return sync(repo, root, a.jobs)
    return 0

if __name__ == '__main__':
    sys.exit(main())
