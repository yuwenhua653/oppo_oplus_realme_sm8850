#!/usr/bin/env python3
"""Freeze the composed full-BQ source/patch/test set after its local review."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from apply_bq import BASE_COMMIT, FULL_BQ, HEADER, PARENT_SHA, apply, pin, require, safe
from test_source import offline_guard_bytes, reconstruct_r84_bq


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-after', required=True, type=Path)
    parser.add_argument('--patch', required=True, type=Path)
    parser.add_argument('--test-contract', required=True, type=Path)
    args = parser.parse_args()
    route = Path(__file__).resolve().parent
    repo = route.parent
    require(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip() == BASE_COMMIT,
            'Freeze only over the exact published R84 repository')
    require(pin((repo / 'r84-build-route/fastcharge-contract.json').read_bytes())['sha256'] == PARENT_SHA,
            'Frozen R84 preparation contract changed')
    after = args.source_after.read_bytes()
    patch_data = args.patch.read_bytes()
    test_contract = json.loads(args.test_contract.read_text())
    require(test_contract.get('schema') == 1 and test_contract.get('review_status') == 'FROZEN_REVIEWED_SOURCE' and
            len(test_contract.get('jobs', [])) == 3 and
            {job['name'] for job in test_contract['jobs']} == {'mac', 'probe', 'control'} and
            all(job['source'] == FULL_BQ and safe(route, job['script']).is_file() for job in test_contract['jobs']),
            'Exact three production suites must exist before freezing')
    peer = test_contract.get('independent_merged')
    require(isinstance(peer, dict) and peer.get('name') == 'merged_peer' and peer.get('source') == FULL_BQ and
            safe(route, peer['script']).is_file(), 'Independent composed production suite must exist')
    guards = [
        {'path': HEADER, 'source': 'r61-build-route/preimage/' + HEADER.removeprefix('vendor/qcom/sm8850/')},
        {'path': 'vendor/qcom/sm8850/drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h',
         'source': 'r61-build-route/payload/drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h'},
        {'path': 'vendor/qcom/sm8850/configs/canoe_perf.bzl',
         'source_parts': ['r78-build-route/audio/preimage/configs/canoe_perf.bzl',
                          'r78-build-route/audio/fragments/canoe_perf.bzl']},
    ]
    for guard in guards:
        guard['expected'] = pin(offline_guard_bytes(repo, guard))
    require(b'"CONFIG_MYRON_IC_FIRMWARE_PROGRAMMING": "n"' in offline_guard_bytes(repo, guards[2]),
            'Firmware-programming source config must remain n')
    patch_path = route / 'patches/bq-full-safety.patch'
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_bytes(patch_data)
    with tempfile.TemporaryDirectory(prefix='r85-freeze-source-') as temporary:
        workspace = Path(temporary)
        before_path = reconstruct_r84_bq(repo, workspace)
        before = before_path.read_bytes()
        require(before != after, 'R85 must contain the actual reviewed source repair')
        source_contract = {'schema': 1, 'review_status': 'FROZEN_REVIEWED_SOURCE',
            'source_repository': 'yuwenhua653/oppo_oplus_realme_sm8850', 'source_commit': BASE_COMMIT,
            'preparation_parent_contract_sha256': PARENT_SHA, 'header_path': HEADER,
            'compile_only': True, 'activation_allowed': False, 'full_charging_control_enabled': False,
            'writes': [{'path': FULL_BQ, 'before': pin(before), 'after': pin(after),
                        'role': 'inactive_full_MCA_validation_only'}],
            'patches': [{'file': 'patches/bq-full-safety.patch', 'working_directory': 'vendor/qcom/sm8850', **pin(patch_data)}],
            'read_only_guards': guards,
            'scope': ['strict bounded MAC/I2C completion and output publication',
                      'validated vendor before mandatory initialization and provider publication',
                      'serialized authentication/MAC/fast-mode transactions and truthful errors'],
            'hardware_control_tested': False}
        write(route / 'SOURCE-CONTRACT.json', source_contract)
        for guard in guards:
            target = safe(workspace, guard['path'])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(offline_guard_bytes(repo, guard))
        apply(workspace, route)
        require(before_path.read_bytes() == after, 'Supplied patch does not yield the exact composed reviewed source')
    write(route / 'TEST-CONTRACT.json', test_contract)
    previous = json.loads((repo / 'r84-build-route/fastcharge-contract.json').read_text())
    contract = {key: previous[key] for key in ('baseline_image_sha256', 'baseline_kernel_release',
                'sources_lock_sha256', 'git_heads', 'core_targets', 'validation_scope',
                'validation_scope_sha256', 'validation_only_modules')}
    contract.update(schema=1, review_status='FROZEN_REVIEWED_SOURCE', base_commit=BASE_COMMIT,
        parent_contract='r84-build-route/fastcharge-contract.json', parent_contract_sha256=PARENT_SHA,
        compile_only=True, flashable=False, hardware_tested=False, activation_allowed=False,
        full_charging_control_enabled=False, runtime_candidate_module_names=[], modules=[],
        source_contract=pin((route / 'SOURCE-CONTRACT.json').read_bytes()),
        experiment='Repair the coherent source full-BQ provider while retaining the accepted R84 runtime; compile the inactive47 once')
    contract['locked_files'] = [{'path': str(path.relative_to(repo)), **pin(path.read_bytes())}
        for path in sorted(route.rglob('*')) if path.is_file() and '__pycache__' not in path.parts and
        path.name != 'build-contract.json']
    write(route / 'build-contract.json', contract)
    digest = pin((route / 'build-contract.json').read_bytes())['sha256']
    workflow = repo / '.github/workflows/build-myron-fastcharge-r85.yml'
    text = workflow.read_text()
    import re
    text, count = re.subn(r"echo '(?:__R85_CONTRACT_SHA256__|[a-f0-9]{64})  r85-build-route/build-contract.json'",
                         "echo '" + digest + "  r85-build-route/build-contract.json'", text)
    require(count == 1, 'Exactly one workflow input contract anchor')
    workflow.write_text(text)
    print(json.dumps({'status': 'R85_INPUTS_FROZEN_PENDING_FULL_VALIDATION',
                      'build_contract': pin((route / 'build-contract.json').read_bytes()),
                      'source_contract': pin((route / 'SOURCE-CONTRACT.json').read_bytes()),
                      'workflow': pin(workflow.read_bytes()), 'locked_files': len(contract['locked_files']),
                      'target_compile_tested': False, 'hardware_tested': False}))


if __name__ == '__main__':
    main()
