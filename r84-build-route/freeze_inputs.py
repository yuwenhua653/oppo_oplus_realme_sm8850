#!/usr/bin/env python3
"""Freeze exactly the reviewed R84 overlay, test and module-selection files."""
import argparse
import json
from pathlib import Path
import re
from apply_fastcharge import BASE_COMMIT, pin, source_contract
from build_fastcharge import PARENT, PARENT_SHA, CANDIDATES


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    repo = args.repo_root.resolve(); route = repo / 'r84-build-route'
    previous = json.loads((repo / PARENT).read_text())
    assert pin((repo / PARENT).read_bytes())['sha256'] == PARENT_SHA
    source_contract(route)
    selection = json.loads((route / 'MODULE-SELECTION.json').read_text())
    c = {k: previous[k] for k in ('baseline_image_sha256', 'baseline_kernel_release', 'sources_lock_sha256', 'git_heads', 'core_targets')}
    c.update({'schema': 1, 'compile_only': True, 'flashable': False, 'hardware_tested': False,
              'base_commit': BASE_COMMIT, 'parent_contract': PARENT, 'parent_contract_sha256': PARENT_SHA,
              'experiment': 'Repair ADC IRQ/work/thermal lifetime publication and collect one bounded manufacturer identity through the owned gauge',
              'runtime_candidate_module_names': sorted(CANDIDATES), 'validation_runtime_candidate_module_names': [],
              'full_charging_control_enabled': False, 'validation_activation_allowed': False,
              'runtime_baseline': {'vendor_boot_sha256': '7fb6f841fa5afa7205dd8cf15b607f8fdff3dfbb38b096ae47c736341ccd950e',
                  'build_id': 'R83-POWER-CACHE-20261021-01', 'user_reported_working': True,
                  'retained_image_sha256': '2fa774b4ffdd75064fb733bb2cad071b02b1813ad5cd54bae32bda2247ef18a7',
                  'retained_core_symvers_sha256': '9d69a48179b0288dbd452dffc061f7754fba09d507fba3086161dfb019c496e3',
                  'myron_mca_readonly_module_sha256': 'd94dcff3fbb52547106d546de874ead15216fc12b24f16c1281008bd2738312a',
                  'myron_bq_readonly_module_sha256': '4644c400eddcfcf5b5cef30c4be0ade866f5e1215df2e43dfa80a810e86d8126',
                  'qti_pmic_glink_module_sha256': '29f97959761de3f2145c5bd8f8a6ef3b1bc1e18196f0c99b3bfbc6b94410aa86',
                  'cnss2_module_sha256': '2cee16815ad9962e82ea8ec833b5a934c6c8de1a6be0c2ee10de0a8bde43ab76',
                  'wlan_module_sha256': 'd987d12125e5dbd82bfa9225741dadb2a8b7fe8ba8078c3588554e999a973598'},
              'modules': selection['candidate_modules'], 'validation_only_modules': selection['validation_only_modules'],
              'validation_scope': 'r61-build-route/runtime-closure-scope.json',
              'validation_scope_sha256': pin((repo / 'r61-build-route/runtime-closure-scope.json').read_bytes())['sha256'],
              'locked_files': []})
    for f in sorted(route.rglob('*')):
        if f.is_file() and '__pycache__' not in f.parts and f.name != 'fastcharge-contract.json':
            assert not f.is_symlink()
            c['locked_files'].append({'path': str(f.relative_to(repo)), **pin(f.read_bytes())})
    file = route / 'fastcharge-contract.json'; file.write_text(json.dumps(c, indent=2) + '\n')
    digest = pin(file.read_bytes())['sha256']
    workflow = repo / '.github/workflows/build-myron-fastcharge-r84.yml'
    data, count = re.subn(r"echo '[A-Za-z0-9_]+  r84-build-route/fastcharge-contract\.json'", "echo '" + digest + "  r84-build-route/fastcharge-contract.json'", workflow.read_text())
    assert count == 1
    workflow.write_text(data)
    print(json.dumps({'contract_sha256': digest, 'locked_files': len(c['locked_files'])}))


if __name__ == '__main__':
    main()
