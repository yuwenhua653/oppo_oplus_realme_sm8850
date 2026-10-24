#!/usr/bin/env python3
"""Validate the single-provider extension without weakening the frozen R90 chain."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import zipfile

BASE_COMMIT = '8dcb57ac2a449595a483912c3de8726ea9df8a32'
PARENT = 'r90-build-route/build-contract.json'
PARENT_SHA = '5064ca52790956bbc024016ef85b19839f83f65a69f42db380cfc9fb67834b26'
PARENT_SOURCE_SHA = '709774666e5c9904d2cc15d80fcce861b9211297beb712e6552ac996f0e81715'
PARENT_ENGINE_SHA = '560fe677fc98497b98576b8626faaef12d4e8fa895f7da09b0e93e614ad8383d'
PREFIX = 'vendor/qcom/sm8850/'
PROVIDER_REL = 'drivers/power/supply/mca/mca_protocol/protocol_pd/qcom_tcpc/qcom_adsp_pd_protocol.c'
PROVIDER = PREFIX + PROVIDER_REL
MODULE = {'module_name': 'qcom_adsp_pd_protocol',
          'target': '//vendor/qcom/sm8850:canoe_perf/' + PROVIDER_REL[:-2],
          'expected_sources': [PROVIDER]}
R12_ZIP_SHA = '3ea4b3acd1481e12ef4f2a65cad8d3e57def245be7b3532489b0c44fd2b80eba'
PROVIDER_BEFORE = {'bytes': 16559, 'sha256': '18d6bb1a2ebe4833f98d2eb73e058a7c81d46cac9f1bb70b6bed3c73f1093762'}
INHERITED_KEYS = ('baseline_image_sha256', 'baseline_kernel_release', 'sources_lock_sha256',
                  'git_heads', 'core_targets')


def require(ok, why):
    if not ok:
        raise ValueError(why)


def pin(data):
    import hashlib
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def safe(root, relative):
    from pathlib import PurePosixPath
    root = Path(root).resolve()
    name = PurePosixPath(relative)
    require(relative and not name.is_absolute() and '..' not in name.parts, 'Unsafe relative path')
    target = root / name
    require(target.resolve().is_relative_to(root), 'Escaping path: ' + relative)
    require(all(not (root / Path(*name.parts[:i])).is_symlink()
                for i in range(1, len(name.parts) + 1)), 'Symlink path: ' + relative)
    return target


def load_r90(repo):
    path = safe(repo, 'r90-build-route/build_temp_schema.py')
    require(pin(path.read_bytes())['sha256'] == PARENT_ENGINE_SHA, 'Frozen R90 engine changed')
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location('r92_frozen_r90', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parents(repo):
    build = safe(repo, PARENT).read_bytes()
    source = safe(repo, 'r90-build-route/SOURCE-CONTRACT.json').read_bytes()
    require(pin(build)['sha256'] == PARENT_SHA, 'Frozen R90 build contract changed')
    require(pin(source)['sha256'] == PARENT_SOURCE_SHA, 'Frozen R90 source contract changed')
    return json.loads(build), json.loads(source)


def r90_snapshot(source):
    result = {row['path']: row['expected'] for row in source['read_only_guards']}
    for row in source['writes']:
        require(row['path'] not in result, 'Duplicate R90 source')
        result[row['path']] = row['after']
    return result


def original_provider(repo):
    path = safe(repo, 'myron-adaptation-r12.zip')
    require(pin(path.read_bytes())['sha256'] == R12_ZIP_SHA, 'Frozen R12 source bundle changed')
    with zipfile.ZipFile(path) as archive:
        data = archive.read('myron-adaptation-r12/drivers/payload/' + PROVIDER_REL)
    require(pin(data) == PROVIDER_BEFORE, 'R12 provider is not the reviewed preimage')
    return data


def source_contract(repo):
    route = safe(repo, 'r92-build-route')
    _, parent_source = parents(repo)
    source = json.loads((route / 'SOURCE-CONTRACT.json').read_bytes())
    require(source.get('schema') == 1 and source.get('source_commit') == BASE_COMMIT and
            source.get('parent_build_contract_sha256') == PARENT_SHA and
            source.get('parent_source_contract_sha256') == PARENT_SOURCE_SHA,
            'Wrong R92 source ancestry')
    require(source.get('compile_only') is True and source.get('activation_allowed') is False and
            source.get('full_charging_control_enabled') is False, 'Inactive compile evidence required')
    rows = source.get('writes', [])
    require(len(rows) == 1 and rows[0]['path'] == PROVIDER and rows[0]['before'] == PROVIDER_BEFORE and
            rows[0]['after'] != rows[0]['before'], 'R92 may patch only the missing PD provider')
    guards = source.get('read_only_guards', [])
    require(len(guards) == len(r90_snapshot(parent_source)) and
            {r['path']: r['expected'] for r in guards} == r90_snapshot(parent_source),
            'All R90 guarded production sources must stay byte-exact')
    patches = source.get('patches', [])
    require(len(patches) == 1 and patches[0]['file'] == 'patches/pd-provider.patch' and
            patches[0]['working_directory'] == PREFIX.rstrip('/'), 'One reviewed provider patch required')
    patch = safe(route, patches[0]['file']).read_bytes()
    require(pin(patch) == {k: patches[0][k] for k in ('bytes', 'sha256')}, 'Provider patch changed')
    headers = [line.split(b'\t', 1)[0] for line in patch.splitlines()
               if line.startswith((b'--- ', b'+++ '))]
    require(headers == [b'--- a/' + PROVIDER_REL.encode(), b'+++ b/' + PROVIDER_REL.encode()],
            'Provider patch touches an undeclared source')
    require(pin((route / 'payload/qcom_adsp_pd_protocol.c').read_bytes()) == rows[0]['after'],
            'Frozen provider payload differs from source postimage')
    require(pin((route / 'preimage/qcom_adsp_pd_protocol.c').read_bytes()) == PROVIDER_BEFORE,
            'Provider negative control changed')
    return source


def check_overlay(repo):
    repo = Path(repo).resolve()
    route = repo / 'r92-build-route'
    parent, _ = parents(repo)
    source_contract(repo)
    c = json.loads((route / 'build-contract.json').read_bytes())
    require(c.get('schema') == 1 and c.get('review_status') == 'FROZEN_REVIEWED_SOURCE' and
            c.get('base_commit') == BASE_COMMIT and c.get('parent_contract') == PARENT and
            c.get('parent_contract_sha256') == PARENT_SHA, 'Wrong R92 build ancestry')
    for key in INHERITED_KEYS:
        require(c.get(key) == parent[key], 'Inherited kernel/toolchain input changed: ' + key)
    require(len(parent['validation_only_modules']) == 47, 'Expected exact R90 47-module parent')
    expected = parent['validation_only_modules'] + [MODULE]
    require(c.get('validation_only_modules') == expected, 'Only one explicit PD provider may extend the scope')
    require(c.get('validation_scope') == 'r92-build-route/module-scope.json', 'Wrong scope document')
    scope = safe(repo, c['validation_scope']).read_bytes()
    require(pin(scope)['sha256'] == c.get('validation_scope_sha256'), 'Scope digest changed')
    require(json.loads(scope) == {'schema': 1, 'parent_scope': parent['validation_scope'],
            'parent_scope_sha256': parent['validation_scope_sha256'], 'added_modules': [MODULE],
            'validation_only_modules': expected}, 'Module scope is not the exact extension')
    require(c.get('compile_only') is True and c.get('flashable') is False and
            c.get('activation_allowed') is False and c.get('full_charging_control_enabled') is False and
            c.get('runtime_candidate_module_names') == [] and c.get('modules') == [],
            'R92 outputs must remain inactive compile evidence')
    require(c.get('source_contract') == pin((route / 'SOURCE-CONTRACT.json').read_bytes()),
            'Source contract not bound')
    rows = c['locked_files']
    names = [row['path'] for row in rows]
    actual = {str(p.relative_to(repo)) for p in route.rglob('*') if p.is_file() and
              '__pycache__' not in p.parts and p.name != 'build-contract.json'}
    require(len(names) == len(set(names)) and set(names) == actual, 'R92 locked file inventory changed')
    for row in rows:
        p = safe(repo, row['path'])
        require(p.is_relative_to(route) and pin(p.read_bytes()) == {k: row[k] for k in ('bytes', 'sha256')},
                'R92 locked input changed: ' + row['path'])
    originals = json.loads((route / 'reference/r90-module-pins.json').read_bytes())
    require(originals['github_commit'] == BASE_COMMIT and originals['github_run_id'] == '40046239434' and
            set(originals['modules']) == {m['module_name'] for m in parent['validation_only_modules']},
            'R90 compiled reference inventory changed')
    return c


def apply(workspace, repo, verify=False):
    root, repo = Path(workspace).resolve(), Path(repo).resolve()
    source = source_contract(repo)
    for row in source['read_only_guards']:
        require(pin(safe(root, row['path']).read_bytes()) == row['expected'], 'R90 source changed: ' + row['path'])
    row = source['writes'][0]
    require(pin(safe(root, PROVIDER).read_bytes()) == row['after' if verify else 'before'],
            'Wrong provider ' + ('postimage' if verify else 'preimage'))
    if not verify:
        patch = source['patches'][0]
        command = ['patch', '--batch', '--fuzz=0', '--forward', '-p1', '-i',
                   str(safe(repo / 'r92-build-route', patch['file']))]
        cwd = safe(root, patch['working_directory'])
        subprocess.run(command + ['--dry-run'], cwd=cwd, check=True, capture_output=True)
        subprocess.run(command, cwd=cwd, check=True, capture_output=True)
        apply(root, repo, verify=True)
    return {'schema': 1, 'status': 'PASS_R92_PROVIDER_POSTIMAGE' if verify else 'PASS_R92_PROVIDER_OVERLAY',
            'writes': source['writes'], 'R90_sources_unchanged': True, 'hardware_tested': False}
