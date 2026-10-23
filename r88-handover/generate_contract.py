#!/usr/bin/env python3
"""Freeze fixed native-loader inputs from an independently reviewed MCA artifact.

The default is a non-activatable draft. A runtime freeze requires an explicit
reviewed R88 CI identity and an ABI report over the same exact artifact.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

BASE_IMAGE = {'bytes': 100663296, 'sha256': 'ade202a830574da27af940c06c828dc1e9b279749b96b524468f24423745cae8'}
BASE_CONTRACT_SHA = 'e68871a2a6654a0c1bd3d0630474e5b79c60281791aeec5f63c1e9d37dbe691e'
KERNEL = '6.12.81-android16-6-maybe-dirty-4k'
SEMANTIC_BEFORE = [
    ('mca_qcom_subpmic_proxy', 'mca_business_charger_comp'),
    ('mca_business_charger_comp', 'mca_business_battery_comp'),
    ('mca_business_battery_comp', 'mca_strategy_fg_comp'),
    ('bq27z561', 'mca_strategy_fg_comp'),
    ('mca_strategy_fg_comp', 'mca_strategy_quickchg'),
    ('sc8581', 'mca_strategy_quickchg'),
    ('mca_business_charger_comp', 'mca_strategy_quickchg'),
]


def need(ok, why):
    if not ok:
        raise ValueError(why)


def pin(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def read(path):
    return json.loads(path.read_text())


def same_pin(path, expected):
    need(path.is_file() and not path.is_symlink() and pin(path.read_bytes()) ==
         {k: expected[k] for k in ('bytes', 'sha256')}, 'Input identity: ' + str(path))


def make_header(contract, digest):
    lines = ['/* Generated from module-set.json; do not edit. */', '#ifndef R88_MCA_CONTRACT_H',
             '#define R88_MCA_CONTRACT_H', '#define BUILD_ID ' + json.dumps(contract['build_id']),
             '#define KERNEL ' + json.dumps(contract['kernel']), '#define CONTRACT_SHA ' + json.dumps(digest),
             '#define RUNTIME_FROZEN ' + str(int(contract['runtime_frozen'])),
             'struct pinned_file { const char *path; uint64_t bytes; const char *sha256; };']
    for key in ('baseline', 'additions'):
        lines.append('static const struct pinned_file ' + key + '[]={')
        for row in contract[key]:
            lines.append('{' + json.dumps(row['path']) + ',' + str(row['bytes']) + 'u,' +
                         json.dumps(row['sha256']) + '},')
        lines.append('};')
        names = 'baseline_names' if key == 'baseline' else 'addition_names'
        lines.append('static const char *' + names + '[]={' + ','.join(json.dumps(r['name']) for r in contract[key]) + '};')
    lines.append('#endif')
    return '\n'.join(lines) + '\n'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime-contract', type=Path, required=True)
    p.add_argument('--baseline-reviews', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--abi', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--build-id', default='R88-MCA-HANDOVER-DRAFT-20261022-01')
    p.add_argument('--freeze-reviewed-r88', action='store_true')
    p.add_argument('--expected-ci-head')
    p.add_argument('--expected-ci-run')
    a = p.parse_args()
    need(not a.out.exists() and re.fullmatch(r'[A-Z0-9-]{8,100}', a.build_id), 'Fresh output and fixed build identity required')
    raw = a.runtime_contract.read_bytes()
    need(pin(raw)['sha256'] == BASE_CONTRACT_SHA, 'Exact healthy R84 runtime contract required')
    base = json.loads(raw)
    need(base['build_id'] == 'R84-THERMAL-FG-QUERY-20261021-01' and len(base['module_files']) == 249,
         'Exact R84 normal249 set required')
    baseline_reviews = read(a.baseline_reviews)
    baseline = []
    for path, row in sorted(base['module_files'].items()):
        need(path.startswith(('/system_dlkm/lib/modules/', '/vendor_dlkm/lib/modules/')),
             'Unexpected normal module path')
        name = Path(path).name.removesuffix('.ko').replace('-', '_')
        actual = baseline_reviews.get(name)
        need(actual and actual['modinfo']['name'] == [name] and
             {k: actual[k] for k in ('bytes', 'sha256')} == {k: row[k] for k in ('bytes', 'sha256')},
             'Actual baseline module metadata: ' + name)
        same_pin(Path(actual['path']), row)
        baseline.append({'name': name, 'path': path, **{k: row[k] for k in ('bytes', 'sha256')}})
    need(len({r['name'] for r in baseline}) == 249 and
         not {'myron_bq_readonly', 'myron_mca_readonly'} & {r['name'] for r in baseline}, 'Unique normal249')
    complete = read(a.candidate / 'validation-complete.json')
    same_pin(a.candidate / 'artifact-lock.json', {'bytes': (a.candidate / 'artifact-lock.json').stat().st_size,
             'sha256': complete['artifact_lock_sha256']})
    lock = read(a.candidate / 'artifact-lock.json')
    for row in lock['files']:
        need(not Path(row['file']).is_absolute() and '..' not in Path(row['file']).parts, 'Safe artifact member')
        same_pin(a.candidate / row['file'], row)
    need(complete['full_validation_success'] is True and complete['required_module_count'] == 47,
         'Complete coherent47 target compilation required')
    abi_raw = a.abi.read_bytes()
    abi = json.loads(abi_raw)
    need(abi['status'] == 'PASS_STATIC_INACTIVE_FULL_MCA_CLOSURE' and
         abi.get('artifact_identity', {}).get('status') == 'PASS_R88_EXACT_ARTIFACT_IDENTITY' and not abi['issues'] and
         not abi['dependency_cycle'] and abi['mca_module_count'] == 47 and
         abi['hypothetical_module_count'] == 294 and abi['retained_vendor_boot']['sha256'] == BASE_IMAGE['sha256'] and
         abi['retained_runtime_contract']['sha256'] == BASE_CONTRACT_SHA and
         abi['source_contract_sha256'] == complete['source_contract_sha256'], 'Same exact retained-kernel ABI review required')
    ci = abi['ci']
    runtime = a.freeze_reviewed_r88
    if runtime:
        need(a.build_id.startswith('R88-') and 'DRAFT' not in a.build_id,
             'Explicit non-draft R88 runtime identity required')
        need(a.expected_ci_head and re.fullmatch('[a-f0-9]{40}', a.expected_ci_head) and
             a.expected_ci_run and a.expected_ci_run.isdecimal() and
             ci['GITHUB_SHA'] == a.expected_ci_head and ci['GITHUB_RUN_ID'] == a.expected_ci_run,
             'Explicit reviewed R88 CI identity required for runtime freeze')
        status_path = a.candidate / 'reports/r88-status.json'
        need(status_path.is_file(), 'Only actual successful R88 outputs may freeze')
        status = read(status_path)
        need(status['github'] == ci and status['success'] is True and status['validation_compiled'] is True,
             'Only actual successful R88 outputs may freeze')
    inventory = read(a.candidate / 'module-inventory.json')
    modules = {r['name']: r for r in inventory['modules']}
    need(len(modules) == 47 and set(modules) == set(abi['mca_checks']), 'Exact full47 module identity')
    names = set(modules) - {'hwid', 'miev'}
    need(len(names) == 45 and not names & {r['name'] for r in baseline}, '45 additions do not replace normal249')
    for name in ('hwid', 'miev'):
        row = modules[name]
        old = next(r for r in baseline if r['name'] == name)
        need({k: row[k] for k in ('bytes', 'sha256')} == {k: old[k] for k in ('bytes', 'sha256')},
             'Retained hwid/miev must be byte-identical to coherent47')
    dependencies = {n: set(abi['mca_checks'][n]['providers']) & names for n in names}
    for before, after in SEMANTIC_BEFORE:
        need(before in names and after in names, 'Semantic ordering target missing')
        dependencies[after].add(before)
    ordered = []
    while dependencies:
        ready = sorted(n for n, deps in dependencies.items() if not deps)
        need(ready, 'Provider/probe ordering cycle')
        ordered.extend(ready)
        for n in ready:
            del dependencies[n]
        for deps in dependencies.values():
            deps.difference_update(ready)
    additions = []
    for name in ordered:
        row = modules[name]
        same_pin(a.candidate / row['file'], row)
        additions.append({'name': name, 'path': '/vendor_dlkm/r32/r88-mca/' + name + '.ko',
                          **{k: row[k] for k in ('bytes', 'sha256')}, 'load_arguments': ''})
    result = {'schema': 1, 'build_id': a.build_id, 'kernel': KERNEL,
              'review_status': 'FROZEN_REVIEWED_R88_RUNTIME_CANDIDATE' if runtime else 'DRAFT_NOT_FOR_RUNTIME',
              'runtime_frozen': runtime, 'activation_allowed': runtime, 'hardware_tested': False,
              'baseline_runtime_contract_sha256': BASE_CONTRACT_SHA, 'baseline_vendor_boot': BASE_IMAGE,
              'normal_module_count': 249, 'total_module_count': 294, 'baseline': baseline, 'additions': additions,
              'source_ci': {'head_sha': ci['GITHUB_SHA'], 'run_id': ci['GITHUB_RUN_ID'],
                            'source_contract_sha256': complete['source_contract_sha256'],
                            'build_contract_sha256': complete['build_contract_sha256']},
              'abi_review': pin(abi_raw), 'semantic_before': SEMANTIC_BEFORE,
              'completion_scope': 'verified file hashes, exact Live set, binding and battery/usb/auth metadata only',
              'auth_success_asserted': False, 'fast_charging_success_asserted': False,
              'failure_policy': 'partial state; no retry, no unload, no old-owner same-boot fallback'}
    a.out.mkdir(parents=True)
    output = json.dumps(result, indent=2, sort_keys=True) + '\n'
    (a.out / 'module-set.json').write_text(output)
    (a.out / 'mca_contract.h').write_text(make_header(result, pin(output.encode())['sha256']))
    print(json.dumps({'status': result['review_status'], 'normal': 249, 'additions': 45, 'total': 294,
                      'module_set': pin(output.encode()), 'activation_allowed': runtime}))


if __name__ == '__main__':
    main()
