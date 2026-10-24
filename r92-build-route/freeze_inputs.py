#!/usr/bin/env python3
"""Freeze reviewed provider code/tests as a one-source patch over exact R90."""
import difflib
import json
from pathlib import Path
import re
import tempfile
from contract import (BASE_COMMIT, INHERITED_KEYS, MODULE, PARENT, PARENT_SHA,
                      PARENT_SOURCE_SHA, PREFIX, PROVIDER, PROVIDER_REL,
                      apply, check_overlay, original_provider, parents, pin,
                      r90_snapshot, require)
from build_pd_provider import reconstruct_parent, write


def main():
    route = Path(__file__).resolve().parent
    repo = route.parent
    previous, parent_source = parents(repo)
    before = original_provider(repo)
    final = (route / 'payload/qcom_adsp_pd_protocol.c').read_bytes()
    require(before != final, 'Provider firmware compatibility patch required')
    require((route / 'tests/provider/run_tests.py').is_file(), 'Actual production provider tests required')
    (route / 'preimage').mkdir(exist_ok=True)
    (route / 'preimage/qcom_adsp_pd_protocol.c').write_bytes(before)
    patch = ''.join(difflib.unified_diff(before.decode().splitlines(keepends=True),
                     final.decode().splitlines(keepends=True),
                     fromfile='a/' + PROVIDER_REL, tofile='b/' + PROVIDER_REL)).encode()
    (route / 'patches').mkdir(exist_ok=True)
    (route / 'patches/pd-provider.patch').write_bytes(patch)
    source = {'schema': 1, 'review_status': 'FROZEN_REVIEWED_SOURCE',
        'source_repository': 'yuwenhua653/oppo_oplus_realme_sm8850', 'source_commit': BASE_COMMIT,
        'parent_build_contract_sha256': PARENT_SHA, 'parent_source_contract_sha256': PARENT_SOURCE_SHA,
        'compile_only': True, 'activation_allowed': False, 'full_charging_control_enabled': False,
        'writes': [{'path': PROVIDER, 'before': pin(before), 'after': pin(final),
                    'role': 'additional_inactive_PD_provider_validation_only'}],
        'read_only_guards': [{'path': name, 'expected': value, 'inherited_R90_postimage': True}
                             for name, value in sorted(r90_snapshot(parent_source).items())],
        'patches': [{'file': 'patches/pd-provider.patch', 'working_directory': PREFIX.rstrip('/'), **pin(patch)}],
        'scope': ['add the missing hardware PD protocol provider to the compiled module selection',
                  'align the provider with reviewed stock firmware property layout and lifecycle',
                  'preserve every R90 production source, kernel/config/toolchain and charging policy'],
        'hardware_control_tested': False}
    write(route / 'SOURCE-CONTRACT.json', source)
    with tempfile.TemporaryDirectory(prefix='r92-freeze-') as temporary:
        workspace = Path(temporary)
        reconstruct_parent(repo, workspace)
        apply(workspace, repo)
        require((workspace / PROVIDER).read_bytes() == final, 'Patch does not reproduce reviewed payload')
    scope = {'schema': 1, 'parent_scope': previous['validation_scope'],
             'parent_scope_sha256': previous['validation_scope_sha256'], 'added_modules': [MODULE],
             'validation_only_modules': previous['validation_only_modules'] + [MODULE]}
    write(route / 'module-scope.json', scope)
    contract = {key: previous[key] for key in INHERITED_KEYS}
    contract.update(schema=1, review_status='FROZEN_REVIEWED_SOURCE', base_commit=BASE_COMMIT,
        parent_contract=PARENT, parent_contract_sha256=PARENT_SHA, compile_only=True, flashable=False,
        hardware_tested=False, activation_allowed=False, full_charging_control_enabled=False,
        runtime_candidate_module_names=[], modules=[], source_contract=pin((route / 'SOURCE-CONTRACT.json').read_bytes()),
        validation_only_modules=scope['validation_only_modules'],
        validation_scope='r92-build-route/module-scope.json',
        validation_scope_sha256=pin((route / 'module-scope.json').read_bytes())['sha256'],
        experiment='Restore the missing ADSP PD/PPS provider over byte-exact R90 module sources')
    contract['locked_files'] = [{'path': str(p.relative_to(repo)), **pin(p.read_bytes())}
        for p in sorted(route.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name != 'build-contract.json']
    write(route / 'build-contract.json', contract)
    workflow = repo / '.github/workflows/build-myron-fastcharge-r92.yml'
    text, count = re.subn(r"echo '(?:__R92_CONTRACT_SHA256__|[a-f0-9]{64})  r92-build-route/build-contract.json'",
        "echo '" + pin((route / 'build-contract.json').read_bytes())['sha256'] + "  r92-build-route/build-contract.json'",
        workflow.read_text())
    require(count == 1, 'One workflow contract anchor required')
    workflow.write_text(text)
    check_overlay(repo)
    print(json.dumps({'status': 'R92_INPUTS_FROZEN_PENDING_VALIDATION',
                      'build_contract': pin((route / 'build-contract.json').read_bytes()),
                      'source_contract': pin((route / 'SOURCE-CONTRACT.json').read_bytes()),
                      'module_count': 48, 'hardware_tested': False}))


if __name__ == '__main__':
    main()
