#!/usr/bin/env python3
"""Verify R79 inputs while retaining the complete, immutable R78 preparation."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import sys

PARENT = 'r78-build-route/multimedia-contract.json'
PARENT_SHA = 'b54e4fef5a8ca1f813e26aecb2b2a034c7917ee24a8c1586ecb90b41e0374233'
BASE_COMMIT = '0758ab6737e71022c250afad539642c2b8aea399'
REQUIRED_MODULES = {'camera', 'msm_drm', 'myron_bq_readonly',
                    'mca_qcom_subpmic_proxy', 'mca_strategy_fg_comp',
                    'mca_platform_fg_ic_ops', 'xiaomi_touch'}

def require(ok, message):
    if not ok:
        raise ValueError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def safe(root, relative, exists=True):
    p = PurePosixPath(relative)
    require(relative and not p.is_absolute() and '..' not in p.parts, 'Unsafe path: ' + relative)
    f = root / p
    require(not f.is_symlink() and f.resolve().is_relative_to(root.resolve()), 'Redirected path: ' + relative)
    require(not exists or f.is_file(), 'Missing input: ' + relative)
    return f

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def parent(repo):
    require(sha(safe(repo, PARENT).read_bytes()) == PARENT_SHA, 'R78 contract changed')
    sys.path.insert(0, str(repo / 'r78-build-route'))
    checker = load('r79_parent_checker', repo / 'r78-build-route/r78_inputs.py')
    c = json.loads((repo / PARENT).read_text())
    checker.check(repo, c)
    return checker, c

def inherited_postimages(repo):
    checker, pc = parent(repo)
    thermal, tc = checker.parent(repo)
    _, _, foundation, prior = thermal.parents(repo)
    base = json.loads((repo / tc['base_contract']).read_text())
    expected = {r['path']: r['sha256'] for r in base['workspace_files']}
    expected.update({r['destination']: r['after_sha256'] for r in prior['writes'] + foundation['writes'] + tc['writes']})
    for name in ('audio', 'display'):
        _, _, component = checker.component(repo, name)
        expected.update({r['destination']: r['after_sha256'] for r in component['writes']})
    return expected

def check(repo, c):
    require(c.get('schema') == 1 and c.get('base_commit') == BASE_COMMIT, 'Wrong R79 base')
    require(c.get('compile_only') is True and c.get('flashable') is False, 'Build cannot approve runtime')
    require(c.get('parent_contract') == PARENT and c.get('parent_contract_sha256') == PARENT_SHA, 'Wrong parent pin')
    _, pc = parent(repo)
    for key in ('baseline_image_sha256', 'baseline_kernel_release', 'sources_lock_sha256', 'git_heads', 'core_targets'):
        require(c.get(key) == pc[key], 'Retained preparation changed: ' + key)
    rows = c['locked_files']
    names = [r['path'] for r in rows]
    own = {str(p.relative_to(repo)) for p in (repo / 'r79-build-route').rglob('*')
           if p.is_file() and '__pycache__' not in p.parts and p.name != 'repair-contract.json'}
    require(len(names) == len(set(names)) and set(names) == own, 'R79 input inventory changed')
    for row in rows:
        data = safe(repo, row['path']).read_bytes()
        require(len(data) == row['bytes'] and sha(data) == row['sha256'], 'R79 input changed: ' + row['path'])
    destinations = []
    expected = inherited_postimages(repo)
    for row in c['writes']:
        destinations.append(row['destination'])
        safe(repo, row['destination'], exists=False)
        require(row['source'] in names, 'Unpinned production source')
        data = safe(repo, row['source']).read_bytes()
        require(sha(data) == row['after_sha256'] and len(data) == row['bytes'], 'Wrong postimage')
        if row['before_sha256'] is not None:
            require(row['preimage_source'] in names, 'Unpinned source preimage')
            require(sha(safe(repo, row['preimage_source']).read_bytes()) == row['before_sha256'], 'Wrong source preimage')
        if row['destination'] in expected:
            require(row['before_sha256'] == expected[row['destination']], 'Overlay does not extend exact R78 postimage')
    require(len(destinations) == len(set(destinations)), 'Overlapping writes')
    require('vendor/qcom/sm8850-modules/qcom/opensource/display-drivers/msm/dsi/myron_flatmode.h' in destinations,
            'Sensor initialization repair is missing')
    modules = c['modules']
    require(c['selected_module_names'] == [m['module_name'] for m in modules], 'Wrong module selection')
    require(len(modules) == len(set(c['selected_module_names'])), 'Duplicate module selection')
    require(set(c['selected_module_names']) == REQUIRED_MODULES, 'Required repair target missing or unexpected')
    require(all(m.get('expected_sources') and m['target'].startswith('//vendor/qcom/') for m in modules), 'Unbound build target')
    source_inputs = {s for m in modules for s in m['expected_sources']}
    require(set(destinations) <= source_inputs, 'Production patch lacks a selected compile action')
    return {'status': 'PASS', 'locked_inputs': len(rows), 'modules': c['selected_module_names'], 'parent_unchanged': True}

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', required=True, type=Path)
    a = p.parse_args()
    repo = a.root.resolve()
    print(json.dumps(check(repo, json.loads((repo / 'r79-build-route/repair-contract.json').read_text())), indent=2))
