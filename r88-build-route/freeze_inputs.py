#!/usr/bin/env python3
"""Freeze a reviewed three-file FG repair against the exact prepared R87."""
import argparse
import difflib
import json
from pathlib import Path
import re
import tempfile
from apply_fg_policy import (BASE_COMMIT, FG_HEADER, PARENT, PARENT_SHA, PARENT_SOURCE_SHA,
                             PREFIX, SOC, STORAGE, STRATEGY, WRITES, apply, pin, require, safe)
from inherit import frozen_r87, parent_postimages, reconstruct_r87


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--strategy', type=Path, required=True)
    parser.add_argument('--header', type=Path, required=True)
    parser.add_argument('--soc-smooth', type=Path, required=True)
    args = parser.parse_args()
    route = Path(__file__).resolve().parent
    repo = route.parent
    r87 = frozen_r87(repo)
    previous, *_ = r87.check(repo)
    expected = parent_postimages(repo)
    parent_source = r87.source_contract(repo / 'r87-build-route')
    guards = [row for row in parent_source['read_only_guards'] if row['path'] not in WRITES]
    guards.extend({'path': row['path'], 'expected': row['after'], 'inherited_r87_postimage': True}
                  for row in parent_source['writes'])
    guards.append({'path': STORAGE, 'expected': {
        'bytes': 33783, 'sha256': '44a70082a3eb052a8bc137f56cb7ca4a854c2560d4b956f1db058eb3bda2b44b'},
        'source': 'r61-build-route/payload/' + STORAGE.removeprefix(PREFIX)})
    require(len({g['path'] for g in guards}) == len(guards), 'Duplicate frozen guard')
    require(all(expected.get(g['path']) == g['expected']['sha256'] for g in guards),
            'Every R88 guard must be an exact R87 postimage')
    after = {STRATEGY: args.strategy.read_bytes(), FG_HEADER: args.header.read_bytes(), SOC: args.soc_smooth.read_bytes()}
    tests = {'schema': 1, 'review_status': 'FROZEN_REVIEWED_SOURCE', 'ASan_UBSan_Werror': True,
             'all_data_is_synthetic': True, 'hardware_tested': False, 'jobs': [{
                 'name': 'fg_policy', 'script': 'tests/fg_policy/run_tests.py',
                 'arguments': ['--source', '{strategy}', '--header', '{strategy_header}',
                               '--soc-smooth', '{soc_smooth}', '--before', '{before_strategy}',
                               '--before-soc-smooth', '{before_soc_smooth}', '--out', '{output}']}]}
    require(all(safe(route, job['script']).is_file() for job in tests['jobs']), 'Reviewed production tests missing')
    with tempfile.TemporaryDirectory(prefix='r88-freeze-') as temporary:
        workspace = Path(temporary)
        reconstruct_r87(repo, workspace)
        writes, patches = [], []
        for path in sorted(WRITES):
            before = safe(workspace, path).read_bytes()
            require(before != after[path], 'Actual R88 repair required: ' + path)
            require(pin(before)['sha256'] == expected[path], 'R88 preimage is not exact R87 source')
            writes.append({'path': path, 'before': pin(before), 'after': pin(after[path]),
                           'role': 'inactive_full_MCA_validation_only'})
            name = path.removeprefix(PREFIX)
            patches.append(''.join(difflib.unified_diff(before.decode().splitlines(keepends=True),
                           after[path].decode().splitlines(keepends=True), fromfile='a/' + name, tofile='b/' + name)))
        patch_data = ''.join(patches).encode()
        patch_path = route / 'patches/fg-policy-separation.patch'
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path.write_bytes(patch_data)
        source = {'schema': 1, 'review_status': 'FROZEN_REVIEWED_SOURCE',
                  'source_repository': 'yuwenhua653/oppo_oplus_realme_sm8850', 'source_commit': BASE_COMMIT,
                  'preparation_parent_contract_sha256': PARENT_SHA, 'parent_source_contract_sha256': PARENT_SOURCE_SHA,
                  'compile_only': True, 'activation_allowed': False, 'full_charging_control_enabled': False,
                  'writes': writes, 'read_only_guards': guards,
                  'patches': [{'file': 'patches/fg-policy-separation.patch', 'working_directory': 'vendor/qcom/sm8850',
                               **pin(patch_data)}], 'hardware_control_tested': False,
                  'scope': ['register real FG telemetry independently of unavailable persistent EU policy',
                            'represent unknown EU policy explicitly without selecting regional SOC or recharge behavior',
                            'retain charger storage gate, authentication, thermal, current and voltage limits']}
        write(route / 'SOURCE-CONTRACT.json', source)
        apply(workspace, route)
        require(all(safe(workspace, path).read_bytes() == data for path, data in after.items()),
                'Patch must yield exact three-file reviewed candidate')
    write(route / 'TEST-CONTRACT.json', tests)
    contract = {key: previous[key] for key in ('baseline_image_sha256', 'baseline_kernel_release',
        'sources_lock_sha256', 'git_heads', 'core_targets', 'validation_scope', 'validation_scope_sha256',
        'validation_only_modules')}
    contract.update(schema=1, review_status='FROZEN_REVIEWED_SOURCE', base_commit=BASE_COMMIT,
        parent_contract=PARENT, parent_contract_sha256=PARENT_SHA, compile_only=True, flashable=False,
        hardware_tested=False, activation_allowed=False, full_charging_control_enabled=False,
        runtime_candidate_module_names=[], modules=[], source_contract=pin((route / 'SOURCE-CONTRACT.json').read_bytes()),
        experiment='Restore physical FG telemetry with explicit unknown persistent EU policy over coherent R87 MCA')
    contract['locked_files'] = [{'path': str(path.relative_to(repo)), **pin(path.read_bytes())}
        for path in sorted(route.rglob('*')) if path.is_file() and '__pycache__' not in path.parts and
        path.name != 'build-contract.json']
    write(route / 'build-contract.json', contract)
    workflow = repo / '.github/workflows/build-myron-fastcharge-r88.yml'
    text, count = re.subn(r"echo '(?:__R88_CONTRACT_SHA256__|[a-f0-9]{64})  r88-build-route/build-contract.json'",
        "echo '" + pin((route / 'build-contract.json').read_bytes())['sha256'] + "  r88-build-route/build-contract.json'",
        workflow.read_text())
    require(count == 1, 'One R88 workflow contract anchor required')
    workflow.write_text(text)
    print(json.dumps({'status': 'R88_INPUTS_FROZEN_PENDING_VALIDATION',
                     'build_contract': pin((route / 'build-contract.json').read_bytes()),
                     'source_contract': pin((route / 'SOURCE-CONTRACT.json').read_bytes()),
                     'workflow': pin(workflow.read_bytes()), 'locked_files': len(contract['locked_files']),
                     'target_compile_tested': False, 'hardware_tested': False}))


if __name__ == '__main__':
    main()
