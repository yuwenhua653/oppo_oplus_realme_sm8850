#!/usr/bin/env python3
"""Apply one reviewed R90 source over byte-exact R89; never relax charging limits."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

BASE_COMMIT = 'fd9b66007d6ab12c2281feb9ad2984b6ca5c4339'
PARENT = 'r89-build-route/build-contract.json'
PARENT_SHA = '68de38814d6b58896b0366f32d5c763f1f6895dd6cbfd3b987846631b0de7cbb'
PARENT_SOURCE_SHA = 'd6c9a364ff008547a4f59cab2d74672955b5d81af5a0a58e7edeb5bce2a61356'
PREFIX = 'vendor/qcom/sm8850/'
BQ = PREFIX + 'drivers/power/supply/mca/mca_hardware_ic/fuelgauge_ic/bq27z561/bq27z561.c'
QUICK = PREFIX + 'drivers/power/supply/mca/mca_strategy/strategy_charger/mca_strategy_quickchg.c'
WRITES = {QUICK}
INHERITED_KEYS = ('baseline_image_sha256', 'baseline_kernel_release', 'sources_lock_sha256',
                  'git_heads', 'core_targets', 'validation_scope', 'validation_scope_sha256',
                  'validation_only_modules')


def require(ok, why):
    if not ok:
        raise ValueError(why)


def pin(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def safe(root, relative):
    root = Path(root).resolve()
    name = PurePosixPath(relative)
    require(relative and not name.is_absolute() and '..' not in name.parts, 'Unsafe relative path')
    target = root / name
    require(target.resolve().is_relative_to(root), 'Escaping path: ' + relative)
    require(all(not (root / Path(*name.parts[:i])).is_symlink()
                for i in range(1, len(name.parts) + 1)), 'Symlink path: ' + relative)
    return target


def parent_contracts(repo):
    build = safe(repo, PARENT).read_bytes()
    source = safe(repo, 'r89-build-route/SOURCE-CONTRACT.json').read_bytes()
    require(pin(build)['sha256'] == PARENT_SHA, 'Frozen R89 build contract changed')
    require(pin(source)['sha256'] == PARENT_SOURCE_SHA, 'Frozen R89 source contract changed')
    return json.loads(build), json.loads(source)


def parent_snapshot_pins(source):
    rows = {row['path']: row['expected'] for row in source['read_only_guards']}
    for row in source['writes']:
        require(row['path'] not in rows, 'Duplicate R89 source path')
        rows[row['path']] = row['after']
    return rows


def source_contract(route):
    route = Path(route).resolve()
    _, parent = parent_contracts(route.parent)
    c = json.loads((route / 'SOURCE-CONTRACT.json').read_bytes())
    require(c.get('schema') == 1 and c.get('source_commit') == BASE_COMMIT and
            c.get('preparation_parent_contract_sha256') == PARENT_SHA and
            c.get('parent_source_contract_sha256') == PARENT_SOURCE_SHA,
            'Wrong R90 source ancestry')
    require(c.get('review_status') == 'FROZEN_REVIEWED_SOURCE' and
            len(c.get('writes', [])) == 1 and {r['path'] for r in c['writes']} == WRITES,
            'R90 may change only the quickchg temperature-table parser')
    require(c.get('compile_only') is True and c.get('activation_allowed') is False and
            c.get('full_charging_control_enabled') is False, 'Inactive compile proof required')
    expected = parent_snapshot_pins(parent)
    guards = c.get('read_only_guards', [])
    require(len(guards) == len(expected) - 1 and
            {r['path']: r['expected'] for r in guards} ==
            {p: v for p, v in expected.items() if p not in WRITES},
            'Every other R89 charging source and configuration must remain unchanged')
    for row in c['writes']:
        require(row['before'] == expected[row['path']] and row['before'] != row['after'],
                'R90 must extend an exact R89 preimage: ' + row['path'])
    require(len(c.get('patches', [])) == 1 and
            c['patches'][0]['file'] == 'patches/quickcharge-temp-table.patch' and
            c['patches'][0]['working_directory'] == PREFIX.rstrip('/'),
            'One exact single-source R90 patch required')
    patch = c['patches'][0]
    data = safe(route, patch['file']).read_bytes()
    require(pin(data) == {k: patch[k] for k in ('bytes', 'sha256')}, 'R90 patch bytes changed')
    headers = [line.split(b'\t', 1)[0] for line in data.splitlines()
               if line.startswith((b'--- ', b'+++ '))]
    require(headers == [prefix + path.removeprefix(PREFIX).encode() for path in sorted(WRITES)
                        for prefix in (b'--- a/', b'+++ b/')],
            'R90 patch may change only the single declared source')
    return c


def check_overlay(repo):
    """Validate this round plus the two parent contract hashes, without replaying parent imports."""
    repo = Path(repo).resolve()
    route = repo / 'r90-build-route'
    previous, _ = parent_contracts(repo)
    source_contract(route)
    c = json.loads((route / 'build-contract.json').read_bytes())
    require(c.get('schema') == 1 and c.get('review_status') == 'FROZEN_REVIEWED_SOURCE' and
            c.get('base_commit') == BASE_COMMIT and c.get('parent_contract') == PARENT and
            c.get('parent_contract_sha256') == PARENT_SHA, 'Wrong R90 build ancestry')
    for key in INHERITED_KEYS:
        require(c.get(key) == previous[key], 'Inherited build scope changed: ' + key)
    require(c.get('compile_only') is True and c.get('flashable') is False and
            c.get('activation_allowed') is False and c.get('full_charging_control_enabled') is False and
            c.get('runtime_candidate_module_names') == [] and c.get('modules') == [],
            'Full MCA outputs must remain inactive compile evidence')
    rows = c['locked_files']
    names = [r['path'] for r in rows]
    actual = {str(p.relative_to(repo)) for p in route.rglob('*') if p.is_file() and
              '__pycache__' not in p.parts and p.name != 'build-contract.json'}
    require(len(names) == len(set(names)) and set(names) == actual, 'R90 locked inventory changed')
    for row in rows:
        path = safe(repo, row['path'])
        require(path.resolve().is_relative_to(route.resolve()) and
                pin(path.read_bytes()) == {k: row[k] for k in ('bytes', 'sha256')},
                'R90 locked input changed: ' + row['path'])
    require(c.get('source_contract') == pin((route / 'SOURCE-CONTRACT.json').read_bytes()),
            'Build contract does not bind the exact R90 source contract')
    inputs = {p for m in c['validation_only_modules'] for p in m['expected_sources']}
    require(WRITES <= inputs, 'Changed source must feed an actually selected module action')
    return c


def apply(workspace, route, verify=False):
    workspace, route = Path(workspace).resolve(), Path(route).resolve()
    c = source_contract(route)
    for row in c['read_only_guards']:
        require(pin(safe(workspace, row['path']).read_bytes()) == row['expected'],
                'R89 source guard changed: ' + row['path'])
    for row in c['writes']:
        require(pin(safe(workspace, row['path']).read_bytes()) == row['after' if verify else 'before'],
                'Wrong R90 ' + ('postimage: ' if verify else 'preimage: ') + row['path'])
    if not verify:
        patch = c['patches'][0]
        command = ['patch', '--batch', '--fuzz=0', '--forward', '-p1', '-i', str(safe(route, patch['file']))]
        cwd = safe(workspace, patch['working_directory'])
        subprocess.run(command + ['--dry-run'], cwd=cwd, check=True, capture_output=True)
        subprocess.run(command, cwd=cwd, check=True, capture_output=True)
        apply(workspace, route, verify=True)
    return {'schema': 1, 'status': 'PASS_R90_EXACT_POSTIMAGES' if verify else 'PASS_R90_EXACT_OVERLAY',
            'writes': c['writes'], 'hardware_tested': False, 'activation_allowed': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo-root', type=Path, required=True)
    p.add_argument('--check-inputs', action='store_true')
    p.add_argument('--workspace', type=Path)
    p.add_argument('--check', action='store_true')
    a = p.parse_args()
    if a.check_inputs:
        c = check_overlay(a.repo_root)
        print(json.dumps({'status': 'PASS_R90_OVERLAY_INPUTS_ONLY', 'locked_inputs': len(c['locked_files']),
                          'full_parent_chain_checked': False}))
    else:
        require(a.workspace is not None, '--workspace required')
        print(json.dumps(apply(a.workspace, a.repo_root / 'r90-build-route', verify=a.check)))
