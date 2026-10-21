#!/usr/bin/env python3
"""Freeze reviewed R83 inputs without modifying any ancestor route."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from build_power import PARENT, PARENT_SHA, TARGET, MODULE, SOURCE_PREFIX
from validation_only import MODULES


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ancestor-repo', type=Path)
    args = parser.parse_args()
    route = Path(__file__).resolve().parent
    repo = route.parent
    ancestor = args.ancestor_repo.resolve() if args.ancestor_repo else repo
    parent_bytes = (ancestor / PARENT).read_bytes()
    assert sha(parent_bytes) == PARENT_SHA
    parent = json.loads(parent_bytes)
    for name in ('SOURCE-CONTRACT.json', 'apply_power.py', 'test_power.py', 'tests/client/run_tests.py'):
        assert (route / name).is_file(), 'Missing final R83 input: ' + name
    source = json.loads((route / 'SOURCE-CONTRACT.json').read_text())
    c = {key: parent[key] for key in ('baseline_image_sha256', 'baseline_kernel_release', 'sources_lock_sha256', 'git_heads', 'core_targets')}
    c.update({
        'schema': 1,
        'base_commit': '45405ec4b75ac71c60f3178d1be24db312fae3ff',
        'parent_contract': PARENT,
        'parent_contract_sha256': PARENT_SHA,
        'compile_only': True,
        'flashable': False,
        'hardware_tested': False,
        'experiment': 'Retain an original still-fresh coherent USB snapshot on narrowly classified transient GET failures; never renew its lifetime',
        'runtime_candidate_module_names': [MODULE],
        'runtime_baseline': {
            'vendor_boot_sha256': 'bbf76ea645db010b5a7842c939f227dada9de85fa9933733e7b08176a4c639ef',
            'retained_image_sha256': '2fa774b4ffdd75064fb733bb2cad071b02b1813ad5cd54bae32bda2247ef18a7',
            'retained_core_symvers_sha256': '9d69a48179b0288dbd452dffc061f7754fba09d507fba3086161dfb019c496e3',
            'myron_mca_readonly_module_sha256': '5d336da04be43186f696e1d62b3de4d27727942471e6d58d480173eda9c72f8f',
            'qti_pmic_glink_module_sha256': '29f97959761de3f2145c5bd8f8a6ef3b1bc1e18196f0c99b3bfbc6b94410aa86',
            'cnss2_module_sha256': '2cee16815ad9962e82ea8ec833b5a934c6c8de1a6be0c2ee10de0a8bde43ab76',
            'wlan_module_sha256': 'd987d12125e5dbd82bfa9225741dadb2a8b7fe8ba8078c3588554e999a973598',
        },
        'modules': [{'target': TARGET, 'module_name': MODULE, 'expected_sources': [SOURCE_PREFIX + 'myron_mca_readonly.c']}],
        'validation_only_modules': MODULES,
        'locked_files': [],
    })
    assert source['source_commit'] == c['base_commit']
    for p in sorted(route.rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts or p.name == 'power-contract.json':
            continue
        assert not p.is_symlink()
        data = p.read_bytes()
        c['locked_files'].append({'path': str(p.relative_to(repo)), 'bytes': len(data), 'sha256': sha(data)})
    contract = route / 'power-contract.json'
    contract.write_text(json.dumps(c, indent=2) + '\n')
    digest = sha(contract.read_bytes())
    workflow = repo / '.github/workflows/build-myron-power-r83.yml'
    text = workflow.read_text()
    text, count = re.subn(r"echo '[A-Za-z0-9_]+  r83-build-route/power-contract\.json'", "echo '" + digest + "  r83-build-route/power-contract.json'", text)
    assert count == 1, 'Workflow must contain one contract hash gate'
    workflow.write_text(text)
    print(json.dumps({'contract_sha256': digest, 'locked_files': len(c['locked_files'])}))


if __name__ == '__main__':
    main()
