#!/usr/bin/env python3
"""Validate the complete R61 source lock before network sync or compilation."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

def require(ok, message):
    if not ok:
        raise ValueError(message)


def safe(root, relative):
    p = PurePosixPath(relative)
    require(relative and not p.is_absolute() and '..' not in p.parts, 'Unsafe input path')
    f = root / p
    require(f.is_file() and not f.is_symlink() and f.resolve().is_relative_to(root), 'Missing/redirected input: ' + relative)
    return f


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check(root, contract):
    require(contract.get('schema') == 1 and contract.get('source_review') == 'PASS', 'R61 source review incomplete')
    require(contract.get('compile_only') is True and contract.get('flashable') is False, 'R61 scope must remain compile only')
    require(contract.get('baseline_kernel_release') == '6.12.81-android16-6-maybe-dirty-4k', 'Wrong baseline release')
    require(contract.get('baseline_image_sha256') == '2fa774b4ffdd75064fb733bb2cad071b02b1813ad5cd54bae32bda2247ef18a7', 'Wrong baseline Image')
    require(contract.get('remote_base_commit') == 'e00bebf6b5bc64ae277b7f52af0eb292744834dc', 'Wrong remote source base')
    records = contract.get('locked_files', [])
    require(records, 'No locked sources')
    locked = {}
    for row in records:
        require(row['path'] not in locked, 'Duplicate source input')
        data = safe(root, row['path']).read_bytes()
        require(sha(data) == row['sha256'] and len(data) == row['bytes'], 'Source bytes/SHA mismatch: ' + row['path'])
        locked[row['path']] = row
    integrated = contract.get('workspace_files', [])
    paths = {row['path'] for row in integrated}
    require(integrated and len(paths) == len(integrated), 'Empty/duplicate integrated lock')
    for row in integrated:
        p = PurePosixPath(row['path'])
        require(not p.is_absolute() and '..' not in p.parts and re.fullmatch(r'[0-9a-f]{64}', row['sha256']), 'Invalid integrated lock')
    modules = contract.get('modules', [])
    require(contract.get('scope_manifest') in locked, 'Unpinned target-scope review')
    scope = json.loads(safe(root, contract['scope_manifest']).read_text())
    names = scope.get('reviewed_module_names', [])
    require(names and len(names) == len(set(names)), 'Empty/duplicate reviewed scope')
    require(len(modules) == len(names) and {r['module_name'] for r in modules} == set(names), 'Targets differ from reviewed module scope')
    diagnostic_names = contract.get('diagnostic_module_names', ['bq27z561', 'camera'])
    require(diagnostic_names == scope.get('reviewed_diagnostic_module_names', ['bq27z561', 'camera']),
            'Unreviewed diagnostic module scope')
    require(len(diagnostic_names) == len(set(diagnostic_names)) and
            {'bq27z561', 'camera'} <= set(diagnostic_names) <= set(names),
            'Diagnostic module scope must preserve BQ and camera')
    generated = {r['output']: r for r in contract.get('generated_files', [])}
    auxiliary = contract.get('auxiliary_providers', [])
    aux_names = [row['module_name'] for row in auxiliary]
    require(len(aux_names) == len(set(aux_names)) and not set(aux_names) & set(names), 'Duplicate auxiliary scope')
    require(set(aux_names) == set(scope.get('reviewed_auxiliary_provider_names', [])), 'Unreviewed auxiliary provider')
    require(contract.get('diagnostic_auxiliary_providers', []) == scope.get('diagnostic_auxiliary_provider_names', []), 'Unreviewed diagnostic provider')
    require(set(contract.get('diagnostic_auxiliary_providers', [])) <= set(aux_names), 'Unknown diagnostic provider')
    closure = contract.get('runtime_closure_modules', [])
    closure_names = [row['module_name'] for row in closure]
    require(set(closure_names) == set(scope.get('reviewed_runtime_closure_module_names', [])),
            'Unreviewed runtime closure scope')
    if closure:
        require(contract.get('runtime_closure_manifest') in locked, 'Unpinned runtime closure source review')
        closure_review = json.loads(safe(root, contract['runtime_closure_manifest']).read_text())
        require(closure_review.get('frozen') is True and closure_review.get('runtime_closure_modules') == closure,
                'Runtime closure targets differ from frozen source review')
        integrated_hashes = {row['path']: row['sha256'] for row in integrated}
        require(closure_review.get('workspace_files') and all(
            integrated_hashes.get(row['path']) == row['sha256']
            for row in closure_review['workspace_files']), 'Runtime closure source hashes not integrated')
    selected = modules + auxiliary + closure
    normalized_names = [row['module_name'].replace('-', '_') for row in selected]
    require(len(normalized_names) == len(set(normalized_names)), 'Duplicate normalized module name')
    for row in selected:
        require(re.fullmatch(r'//[A-Za-z0-9_./+-]+:[A-Za-z0-9_./+-]+', row['target']), 'Invalid target')
        for key, ending in [('output', '.ko'), ('symvers', '.symvers')]:
            p = PurePosixPath(row[key])
            require(not p.is_absolute() and '..' not in p.parts and row[key].startswith('bazel-out/') and row[key].endswith(ending), 'Invalid output')
        require(row.get('expected_sources') and set(row['expected_sources']) <= paths, 'Unlocked module source')
        require(set(row.get('generated_inputs', [])) <= set(generated), 'Unpinned generated module input')
    require(len({r['target'] for r in selected}) == len(selected), 'Duplicate target')
    require(len({r['output'] for r in selected}) == len(selected), 'Duplicate KO output')
    require(len({r['symvers'] for r in selected}) == len(selected), 'Duplicate symvers output')
    for key in ('script', 'lock'):
        require(contract['integration'][key] in locked, 'Unpinned integration ' + key)
    write_lock = json.loads(safe(root, contract['integration']['lock']).read_text())
    require(write_lock.get('schema') == 1 and write_lock.get('writes') and write_lock.get('git_heads'), 'Invalid write lock')
    upstream = {r['repo'] + '/' + r['path'] for r in write_lock.get('upstream_files', [])}
    for row in write_lock.get('upstream_files', []):
        require(row['repo'] in write_lock['git_heads'], 'Unpinned upstream repository')
        require(row['source'] in locked and locked[row['source']]['sha256'] == row['sha256'], 'Unpinned upstream header reference')
    require(contract.get('prerequisite_contract') in locked, 'Unpinned R60 prerequisite contract')
    for row in generated.values():
        require(row['source'] in upstream, 'Generated input lacks pinned Git-tree source')
    destinations = set()
    by_path = {row['path']: row['sha256'] for row in integrated}
    for row in write_lock['writes']:
        require(row['destination'] not in destinations, 'Duplicate write destination')
        destinations.add(row['destination'])
        require(row['source'] in locked and locked[row['source']]['sha256'] == row['after_sha256'], 'Unpinned postimage')
        require(by_path.get(row['destination']) == row['after_sha256'], 'Write missing from integrated source contract')
        if row['before_sha256'] is None:
            require(row.get('preimage') is None, 'New file unexpectedly has preimage')
        else:
            require(row.get('preimage') in locked and locked[row['preimage']]['sha256'] == row['before_sha256'], 'Unpinned exact preimage bytes')
    return {'schema': 1, 'status': 'PASS', 'compile_only': True, 'locked_files': len(locked),
            'writes': len(destinations), 'targets': [r['target'] for r in modules],
            'auxiliary_providers': aux_names,
            'runtime_closure_modules': closure_names,
            'scope': 'Input readiness only; kernel compile, ABI and device behavior are not claimed.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--contract', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(check(a.root.resolve(), json.loads(a.contract.read_text())), indent=2))
