#!/usr/bin/env python3
"""Freeze reviewed CP and quickchg error repair over the exact successful R86."""
import argparse
import difflib
import json
from pathlib import Path
import re
import tempfile
from apply_safety import (BASE_COMMIT, CP, FG_HEADER, GLINK, PARENT, PARENT_SHA, PARENT_SOURCE_SHA,
                          PREFIX, QUICKCHG, SUBPMIC, USB, WRITES, apply, pin, require, safe)
from build_safety import frozen_r86, write
from test_source import guard_bytes, reconstruct_r86


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cp', type=Path, required=True)
    parser.add_argument('--quickchg', type=Path, required=True)
    args = parser.parse_args()
    route = Path(__file__).resolve().parent
    repo = route.parent
    r86 = frozen_r86(repo)
    previous, _, pc, parent_inputs, _, r84, r85 = r86.check(repo)
    previous_source = r86.source_contract(repo / 'r86-build-route')
    old_test = r85.load('r87_freeze_guard_recipe', repo / 'r85-build-route/test_source.py')
    guards = list(previous_source['read_only_guards'])
    guards.extend({'path': row['path'], 'expected': row['after'], 'inherited_r86_postimage': True}
                  for row in previous_source['writes'] if row['path'] not in WRITES)
    guards.extend([
        {'path': USB, 'expected': {'bytes': 6535, 'sha256': 'efb237b5f3fed68faf4eecc4510b6c1aec0e0dc2a7e116ed8a20434450da551e'},
         'inherited_r86_postimage': True},
        {'path': FG_HEADER, 'source': 'r87-build-route/preimage/strategy_fg.h',
         'expected': pin((route / 'preimage/strategy_fg.h').read_bytes())},
        {'path': GLINK, 'source': 'r76-build-route/payload/' + GLINK.removeprefix(PREFIX),
         'expected': pin(safe(repo, 'r76-build-route/payload/' + GLINK.removeprefix(PREFIX)).read_bytes())},
        {'path': SUBPMIC, 'source': 'r79-build-route/charge/payload/' + SUBPMIC.removeprefix(PREFIX),
         'expected': pin(safe(repo, 'r79-build-route/charge/payload/' + SUBPMIC.removeprefix(PREFIX)).read_bytes())},
    ])
    expected = r86.parent_postimages(repo, pc, parent_inputs, r84, r85)
    for row in previous_source['writes']:
        expected[row['path']] = row['after']['sha256']
    require(all(expected.get(g['path']) == g['expected']['sha256'] for g in guards),
            'Every new guard must be an exact frozen R86 postimage')
    require(b'"CONFIG_MYRON_IC_FIRMWARE_PROGRAMMING": "n"' in
            old_test.offline_guard_bytes(repo, next(g for g in guards if g['path'] == PREFIX + 'configs/canoe_perf.bzl')),
            'Firmware programming source config must remain n')
    after = {CP: args.cp.read_bytes(), QUICKCHG: args.quickchg.read_bytes()}
    tests = {'schema': 1, 'review_status': 'FROZEN_REVIEWED_SOURCE', 'ASan_UBSan_Werror': True,
             'all_data_is_synthetic': True, 'hardware_tested': False, 'jobs': [
                 {'name': 'cp', 'script': 'tests/cp/run_tests.py',
                  'arguments': ['--source', '{cp}', '--before', '{before_cp}', '--out', '{output}']},
                 {'name': 'quickchg', 'script': 'tests/quickchg/run_tests.py',
                  'arguments': ['--source', '{quickchg}', '--before', '{before_quickchg}', '--out', '{output}']},
                 {'name': 'fanout', 'script': 'tests/fanout/run_tests.py',
                  'arguments': ['--quickchg', '{quickchg}', '--bq', '{bq}', '--strategy', '{strategy}',
                                '--strategy-header', '{strategy_header}', '--out', '{output}']}]}
    require(all(safe(route, job['script']).is_file() for job in tests['jobs']), 'Reviewed production tests missing')
    with tempfile.TemporaryDirectory(prefix='r87-freeze-') as temporary:
        workspace = Path(temporary)
        reconstruct_r86(repo, workspace)
        writes = []
        patches = []
        for path in sorted(WRITES):
            before = safe(workspace, path).read_bytes()
            require(before != after[path], 'Actual R87 repair required: ' + path)
            require(pin(before)['sha256'] == expected[path], 'R87 preimage is not exact frozen R86 source')
            writes.append({'path': path, 'before': pin(before), 'after': pin(after[path]),
                           'role': 'inactive_full_MCA_validation_only'})
            name = path.removeprefix(PREFIX)
            patches.append(''.join(difflib.unified_diff(before.decode().splitlines(keepends=True),
                           after[path].decode().splitlines(keepends=True), fromfile='a/' + name, tofile='b/' + name)))
        patch_data = ''.join(patches).encode()
        patch_path = route / 'patches/charging-error-safety.patch'
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path.write_bytes(patch_data)
        source = {'schema': 1, 'review_status': 'FROZEN_REVIEWED_SOURCE',
                  'source_repository': 'yuwenhua653/oppo_oplus_realme_sm8850', 'source_commit': BASE_COMMIT,
                  'preparation_parent_contract_sha256': PARENT_SHA, 'parent_source_contract_sha256': PARENT_SOURCE_SHA,
                  'compile_only': True, 'activation_allowed': False, 'full_charging_control_enabled': False,
                  'writes': writes, 'read_only_guards': guards,
                  'patches': [{'file': 'patches/charging-error-safety.patch', 'working_directory': 'vendor/qcom/sm8850',
                               **pin(patch_data)}], 'hardware_control_tested': False,
                  'scope': ['propagate mandatory CP setup, protection, ADC and probe failures',
                            'do not advance adapter voltage after failed CP reads, enables or protocol requests',
                            'validate single and parallel FG fanout using the exact production enum']}
        write(route / 'SOURCE-CONTRACT.json', source)
        for guard in guards:
            target = safe(workspace, guard['path'])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(guard_bytes(repo, workspace, guard, old_test))
        apply(workspace, route)
        require(all(safe(workspace, path).read_bytes() == data for path, data in after.items()),
                'Patch must yield the exact two-file reviewed candidate')
    write(route / 'TEST-CONTRACT.json', tests)
    contract = {key: previous[key] for key in ('baseline_image_sha256', 'baseline_kernel_release',
        'sources_lock_sha256', 'git_heads', 'core_targets', 'validation_scope', 'validation_scope_sha256',
        'validation_only_modules')}
    contract.update(schema=1, review_status='FROZEN_REVIEWED_SOURCE', base_commit=BASE_COMMIT,
        parent_contract=PARENT, parent_contract_sha256=PARENT_SHA, compile_only=True, flashable=False,
        hardware_tested=False, activation_allowed=False, full_charging_control_enabled=False,
        runtime_candidate_module_names=[], modules=[], source_contract=pin((route / 'SOURCE-CONTRACT.json').read_bytes()),
        experiment='Verify mandatory CP and voltage-tuning errors in the coherent inactive47; retain accepted R84 runtime')
    contract['locked_files'] = [{'path': str(path.relative_to(repo)), **pin(path.read_bytes())}
        for path in sorted(route.rglob('*')) if path.is_file() and '__pycache__' not in path.parts and
        path.name != 'build-contract.json']
    write(route / 'build-contract.json', contract)
    workflow = repo / '.github/workflows/build-myron-fastcharge-r87.yml'
    text, count = re.subn(r"echo '(?:__R87_CONTRACT_SHA256__|[a-f0-9]{64})  r87-build-route/build-contract.json'",
        "echo '" + pin((route / 'build-contract.json').read_bytes())['sha256'] + "  r87-build-route/build-contract.json'",
        workflow.read_text())
    require(count == 1, 'One R87 workflow input contract anchor')
    workflow.write_text(text)
    print(json.dumps({'status': 'R87_INPUTS_FROZEN_PENDING_VALIDATION',
                     'build_contract': pin((route / 'build-contract.json').read_bytes()),
                     'source_contract': pin((route / 'SOURCE-CONTRACT.json').read_bytes()),
                     'workflow': pin(workflow.read_bytes()), 'locked_files': len(contract['locked_files']),
                     'target_compile_tested': False, 'hardware_tested': False}))


if __name__ == '__main__':
    main()
