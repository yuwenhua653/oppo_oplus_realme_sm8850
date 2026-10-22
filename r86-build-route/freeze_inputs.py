#!/usr/bin/env python3
"""Freeze reviewed R86 source, production tests and workflow over exact R85."""
import argparse
import difflib
import json
from pathlib import Path
import re
import tempfile
from apply_control import (BASE_COMMIT, FULL_BQ, HEADER, PARENT, PARENT_SHA, PARENT_SOURCE_SHA,
                           PREFIX, QUICKCHG, STRATEGY, WRITES, apply, pin, require, safe)
from build_control import frozen_r85, write
from test_source import reconstruct_r85


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bq', type=Path, required=True)
    parser.add_argument('--header', type=Path, required=True)
    parser.add_argument('--quickchg', type=Path, required=True)
    args = parser.parse_args()
    route = Path(__file__).resolve().parent
    repo = route.parent
    r85 = frozen_r85(repo)
    previous, _, _, _, _, _ = r85.check(repo)
    old_test = r85.load('r86_freeze_old_tests', repo / 'r85-build-route/test_source.py')
    previous_source = r85.source_contract(repo / 'r85-build-route')
    guards = [row for row in previous_source['read_only_guards'] if row['path'] != HEADER]
    strategy_source = 'r79-build-route/fg/payload/' + STRATEGY.removeprefix(PREFIX)
    guards.append({'path': STRATEGY, 'source': strategy_source, 'expected': pin(safe(repo, strategy_source).read_bytes())})
    require(b'"CONFIG_MYRON_IC_FIRMWARE_PROGRAMMING": "n"' in
            old_test.offline_guard_bytes(repo, next(g for g in guards if g['path'] == PREFIX + 'configs/canoe_perf.bzl')),
            'Firmware-programming source config must remain n')
    after = {FULL_BQ: args.bq.read_bytes(), HEADER: args.header.read_bytes(), QUICKCHG: args.quickchg.read_bytes()}
    tests = {'schema': 1, 'review_status': 'FROZEN_REVIEWED_SOURCE', 'ASan_UBSan_Werror': True,
             'all_data_is_synthetic': True, 'hardware_tested': False, 'jobs': [
                 {'name': 'bq_mode', 'script': 'tests/bq/run_tests.py',
                  'arguments': ['--source', '{bq}', '--before', '{before_bq}', '--out', '{output}']},
                 {'name': 'quickchg', 'script': 'tests/quickchg/run_tests.py',
                  'arguments': ['--quickchg', '{quickchg}', '--bq', '{bq}', '--strategy', '{strategy}',
                                '--before-quickchg', '{before_quickchg}', '--out', '{output}']}]}
    for job in tests['jobs']:
        require(safe(route, job['script']).is_file(), 'Reviewed production test is missing')
    with tempfile.TemporaryDirectory(prefix='r86-freeze-') as temporary:
        workspace = Path(temporary)
        reconstruct_r85(repo, workspace)
        writes = []
        patches = []
        for path in sorted(WRITES):
            before = safe(workspace, path).read_bytes()
            require(before != after[path], 'R86 must contain the reviewed change for ' + path)
            writes.append({'path': path, 'before': pin(before), 'after': pin(after[path]),
                           'role': 'inactive_full_MCA_validation_only'})
            name = path.removeprefix(PREFIX)
            patches.append(''.join(difflib.unified_diff(before.decode().splitlines(keepends=True),
                           after[path].decode().splitlines(keepends=True), fromfile='a/' + name, tofile='b/' + name)))
        patch_data = ''.join(patches).encode()
        patch_path = route / 'patches/fastcharge-state.patch'
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path.write_bytes(patch_data)
        source = {'schema': 1, 'review_status': 'FROZEN_REVIEWED_SOURCE',
                  'source_repository': 'yuwenhua653/oppo_oplus_realme_sm8850', 'source_commit': BASE_COMMIT,
                  'preparation_parent_contract_sha256': PARENT_SHA, 'parent_source_contract_sha256': PARENT_SOURCE_SHA,
                  'compile_only': True, 'activation_allowed': False, 'full_charging_control_enabled': False,
                  'writes': writes, 'read_only_guards': guards,
                  'patches': [{'file': 'patches/fastcharge-state.patch', 'working_directory': 'vendor/qcom/sm8850',
                               **pin(patch_data)}], 'hardware_control_tested': False,
                  'scope': ['wire-confirmed initial mode cache and truthful unknown reads',
                            'quick-charge caller failure cleanup and provider-driven retry']}
        write(route / 'SOURCE-CONTRACT.json', source)
        for guard in guards:
            target = safe(workspace, guard['path'])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(old_test.offline_guard_bytes(repo, guard))
        apply(workspace, route)
        require(all(safe(workspace, p).read_bytes() == b for p, b in after.items()),
                'Patch must produce the exact reviewed three-file candidate')
    write(route / 'TEST-CONTRACT.json', tests)
    contract = {key: previous[key] for key in ('baseline_image_sha256', 'baseline_kernel_release',
        'sources_lock_sha256', 'git_heads', 'core_targets', 'validation_scope', 'validation_scope_sha256',
        'validation_only_modules')}
    contract.update(schema=1, review_status='FROZEN_REVIEWED_SOURCE', base_commit=BASE_COMMIT,
        parent_contract=PARENT, parent_contract_sha256=PARENT_SHA, compile_only=True, flashable=False,
        hardware_tested=False, activation_allowed=False, full_charging_control_enabled=False,
        runtime_candidate_module_names=[], modules=[], source_contract=pin((route / 'SOURCE-CONTRACT.json').read_bytes()),
        experiment='Verify mode initialization and error cleanup within the coherent inactive47; retain accepted R84 runtime')
    contract['locked_files'] = [{'path': str(path.relative_to(repo)), **pin(path.read_bytes())}
        for path in sorted(route.rglob('*')) if path.is_file() and '__pycache__' not in path.parts and
        path.name != 'build-contract.json']
    write(route / 'build-contract.json', contract)
    workflow = repo / '.github/workflows/build-myron-fastcharge-r86.yml'
    text, count = re.subn(r"echo '(?:__R86_CONTRACT_SHA256__|[a-f0-9]{64})  r86-build-route/build-contract.json'",
        "echo '" + pin((route / 'build-contract.json').read_bytes())['sha256'] + "  r86-build-route/build-contract.json'",
        workflow.read_text())
    require(count == 1, 'Exactly one R86 workflow input contract anchor')
    workflow.write_text(text)
    print(json.dumps({'status': 'R86_INPUTS_FROZEN_PENDING_VALIDATION',
                     'build_contract': pin((route / 'build-contract.json').read_bytes()),
                     'source_contract': pin((route / 'SOURCE-CONTRACT.json').read_bytes()),
                     'workflow': pin(workflow.read_bytes()), 'locked_files': len(contract['locked_files']),
                     'target_compile_tested': False, 'hardware_tested': False}))


if __name__ == '__main__':
    main()
