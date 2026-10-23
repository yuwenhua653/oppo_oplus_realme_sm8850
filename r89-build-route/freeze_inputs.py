#!/usr/bin/env python3
"""Freeze R89 from the archived compiled R88 snapshot; preserve exact file bytes."""
import argparse
import difflib
import json
from pathlib import Path
import re
import shutil
import tempfile
from apply_probe_recovery import (BASE_COMMIT, BQ, INHERITED_KEYS, PARENT, PARENT_SHA,
                                  PARENT_SOURCE_SHA, PREFIX, QUICK, WRITES, apply,
                                  check_overlay, parent_contracts, parent_snapshot_pins,
                                  pin, require, safe)


def write(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before-root', type=Path, required=True)
    parser.add_argument('--bq', type=Path, required=True)
    parser.add_argument('--quick', type=Path, required=True)
    args = parser.parse_args()
    route = Path(__file__).resolve().parent
    repo = route.parent
    previous, parent_source = parent_contracts(repo)
    expected = parent_snapshot_pins(parent_source)
    after = {BQ: args.bq.read_bytes(), QUICK: args.quick.read_bytes()}
    require((route / 'test_source.py').is_file(), 'R89 production test entry point missing')
    writes, patches = [], []
    for name in sorted(WRITES):
        before = safe(args.before_root, name).read_bytes()
        require(pin(before) == expected[name], 'Snapshot is not exact compiled R88: ' + name)
        require(before != after[name], 'Expected an actual R89 change: ' + name)
        writes.append({'path': name, 'before': pin(before), 'after': pin(after[name]),
                       'role': 'inactive_full_MCA_validation_only'})
        suffix = name.removeprefix(PREFIX)
        patches.append(''.join(difflib.unified_diff(before.decode('utf-8').splitlines(keepends=True),
                       after[name].decode('utf-8').splitlines(keepends=True),
                       fromfile='a/' + suffix, tofile='b/' + suffix)))
    data = ''.join(patches).encode('utf-8')
    patch_file = route / 'patches/quickcharge-init.patch'
    patch_file.parent.mkdir(parents=True, exist_ok=True)
    patch_file.write_bytes(data)
    guards = [{'path': name, 'expected': value, 'inherited_r88_postimage': True}
              for name, value in sorted(expected.items()) if name not in WRITES]
    source = {'schema': 1, 'review_status': 'FROZEN_REVIEWED_SOURCE',
              'source_repository': 'yuwenhua653/oppo_oplus_realme_sm8850', 'source_commit': BASE_COMMIT,
              'preparation_parent_contract_sha256': PARENT_SHA, 'parent_source_contract_sha256': PARENT_SOURCE_SHA,
              'compile_only': True, 'activation_allowed': False, 'full_charging_control_enabled': False,
              'writes': writes, 'read_only_guards': guards,
              'patches': [{'file': 'patches/quickcharge-init.patch', 'working_directory': PREFIX.rstrip('/'),
                           **pin(data)}], 'hardware_control_tested': False,
              'scope': ['retry missing BQ battery metadata without fabricating an identity',
                        'expose quickchg initialization stage and original errors without requiring a bound device',
                        'retain R88 FG behavior, storage gate, authentication, battery-table matching and all charging limits']}
    write(route / 'SOURCE-CONTRACT.json', source)
    with tempfile.TemporaryDirectory(prefix='r89-freeze-') as temporary:
        workspace = Path(temporary)
        for name, expected_pin in expected.items():
            original = safe(args.before_root, name)
            require(pin(original.read_bytes()) == expected_pin, 'Wrong inherited R88 snapshot: ' + name)
            destination = safe(workspace, name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, destination)
        apply(workspace, route)
        require(all(safe(workspace, name).read_bytes() == value for name, value in after.items()),
                'Frozen patch did not produce the exact reviewed sources')
    contract = {key: previous[key] for key in INHERITED_KEYS}
    contract.update(schema=1, review_status='FROZEN_REVIEWED_SOURCE', base_commit=BASE_COMMIT,
        parent_contract=PARENT, parent_contract_sha256=PARENT_SHA, compile_only=True, flashable=False,
        hardware_tested=False, activation_allowed=False, full_charging_control_enabled=False,
        runtime_candidate_module_names=[], modules=[], source_contract=pin((route / 'SOURCE-CONTRACT.json').read_bytes()),
        experiment='Recover missing cell identity metadata and expose quickchg initialization failure over exact R88')
    contract['locked_files'] = [{'path': str(path.relative_to(repo)), **pin(path.read_bytes())}
        for path in sorted(route.rglob('*')) if path.is_file() and '__pycache__' not in path.parts and
        path.name != 'build-contract.json']
    write(route / 'build-contract.json', contract)
    workflow = repo / '.github/workflows/build-myron-fastcharge-r89.yml'
    if workflow.is_file():
        text, count = re.subn(r"echo '(?:__R89_CONTRACT_SHA256__|[a-f0-9]{64})  r89-build-route/build-contract.json'",
            "echo '" + pin((route / 'build-contract.json').read_bytes())['sha256'] + "  r89-build-route/build-contract.json'",
            workflow.read_text())
        require(count == 1, 'One R89 workflow contract anchor required')
        workflow.write_text(text)
    check_overlay(repo)
    print(json.dumps({'status': 'R89_OVERLAY_FROZEN_PENDING_VALIDATION',
                      'build_contract': pin((route / 'build-contract.json').read_bytes()),
                      'source_contract': pin((route / 'SOURCE-CONTRACT.json').read_bytes()),
                      'locked_files': len(contract['locked_files']),
                      'full_parent_chain_checked': False, 'hardware_tested': False}))


if __name__ == '__main__':
    main()
