#!/usr/bin/env python3
"""Freeze the reviewed R90 patch over an exact locally reconstructed R89 snapshot."""
import json
from pathlib import Path
import re
import tempfile
from apply_temp_schema import (BASE_COMMIT, INHERITED_KEYS, PARENT, PARENT_SHA,
                               PARENT_SOURCE_SHA, PREFIX, QUICK, apply, check_overlay,
                               parent_contracts, parent_snapshot_pins, pin, require, safe)
from build_temp_schema import reconstruct_parent, write


def main():
    route = Path(__file__).resolve().parent
    repo = route.parent
    previous, parent_source = parent_contracts(repo)
    expected = parent_snapshot_pins(parent_source)
    patch_name = 'patches/quickcharge-temp-table.patch'
    patch = safe(route, patch_name).read_bytes()
    require(pin((route / 'preimage/mca_strategy_quickchg.c').read_bytes()) == expected[QUICK],
            'R90 negative-control preimage must be exact R89')
    require((route / 'test_source.py').is_file(), 'R90 production test entry point missing')
    import subprocess
    with tempfile.TemporaryDirectory(prefix='r90-freeze-') as temporary:
        workspace = Path(temporary)
        reconstruct_parent(repo, workspace)
        command = ['patch', '--batch', '--fuzz=0', '--forward', '-p1', '-i', str(safe(route, patch_name))]
        cwd = safe(workspace, PREFIX.rstrip('/'))
        subprocess.run(command + ['--dry-run'], cwd=cwd, check=True, capture_output=True)
        subprocess.run(command, cwd=cwd, check=True, capture_output=True)
        after = pin(safe(workspace, QUICK).read_bytes())
        require(after != expected[QUICK], 'R90 must make an actual production source change')
        source = {'schema': 1, 'review_status': 'FROZEN_REVIEWED_SOURCE',
            'source_repository': 'yuwenhua653/oppo_oplus_realme_sm8850', 'source_commit': BASE_COMMIT,
            'preparation_parent_contract_sha256': PARENT_SHA, 'parent_source_contract_sha256': PARENT_SOURCE_SHA,
            'compile_only': True, 'activation_allowed': False, 'full_charging_control_enabled': False,
            'writes': [{'path': QUICK, 'before': expected[QUICK], 'after': after,
                        'role': 'inactive_full_MCA_validation_only'}],
            'read_only_guards': [{'path': name, 'expected': value, 'inherited_r89_postimage': True}
                                 for name, value in sorted(expected.items()) if name != QUICK],
            'patches': [{'file': patch_name, 'working_directory': PREFIX.rstrip('/'), **pin(patch)}],
            'hardware_control_tested': False,
            'scope': ['parse supported 9-column and 11-column quickcharge temperature tables',
                      'retain strict malformed-table rejection and battery-table selection',
                      'retain R89 metadata recovery, R88 FG policy separation and all charging protections']}
        write(route / 'SOURCE-CONTRACT.json', source)
        apply(workspace, route, verify=True)
    contract = {key: previous[key] for key in INHERITED_KEYS}
    contract.update(schema=1, review_status='FROZEN_REVIEWED_SOURCE', base_commit=BASE_COMMIT,
        parent_contract=PARENT, parent_contract_sha256=PARENT_SHA, compile_only=True, flashable=False,
        hardware_tested=False, activation_allowed=False, full_charging_control_enabled=False,
        runtime_candidate_module_names=[], modules=[], source_contract=pin((route / 'SOURCE-CONTRACT.json').read_bytes()),
        experiment='Repair quickchg temperature-table schema parsing over exact R89')
    contract['locked_files'] = [{'path': str(path.relative_to(repo)), **pin(path.read_bytes())}
        for path in sorted(route.rglob('*')) if path.is_file() and '__pycache__' not in path.parts and
        path.name != 'build-contract.json']
    write(route / 'build-contract.json', contract)
    workflow = repo / '.github/workflows/build-myron-fastcharge-r90.yml'
    text, count = re.subn(r"echo '(?:__R90_CONTRACT_SHA256__|[a-f0-9]{64})  r90-build-route/build-contract.json'",
        "echo '" + pin((route / 'build-contract.json').read_bytes())['sha256'] + "  r90-build-route/build-contract.json'",
        workflow.read_text())
    require(count == 1, 'One R90 workflow contract anchor required')
    workflow.write_text(text)
    check_overlay(repo)
    print(json.dumps({'status': 'R90_OVERLAY_FROZEN_PENDING_VALIDATION',
        'build_contract': pin((route / 'build-contract.json').read_bytes()),
        'source_contract': pin((route / 'SOURCE-CONTRACT.json').read_bytes()),
        'locked_files': len(contract['locked_files']), 'hardware_tested': False}))


if __name__ == '__main__':
    main()
