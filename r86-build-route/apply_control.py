#!/usr/bin/env python3
"""Apply the exact three-file R86 overlay to the frozen successful R85 source."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

BASE_COMMIT = '9c932f7bc81d045e803f3b639fa12c9cf7f63a73'
PARENT = 'r85-build-route/build-contract.json'
PARENT_SHA = 'f5ce42e231837c8e11b07665529ce39e878ae8fb14445ebc8bde756fc9f77329'
PARENT_SOURCE_SHA = '7ae5acfcff6b7def1f0b2d0a74b74f3b33c51c1b332d008dd711b585e054353b'
PREFIX = 'vendor/qcom/sm8850/'
FULL_BQ = PREFIX + 'drivers/power/supply/mca/mca_hardware_ic/fuelgauge_ic/bq27z561/bq27z561.c'
HEADER = PREFIX + 'drivers/power/supply/mca/mca_hardware_ic/fuelgauge_ic/bq27z561/inc/bq27z561.h'
QUICKCHG = PREFIX + 'drivers/power/supply/mca/mca_strategy/strategy_charger/mca_strategy_quickchg.c'
STRATEGY = PREFIX + 'drivers/power/supply/mca/mca_strategy/strategy_fg/mca_strategy_fg.c'
WRITES = {FULL_BQ, HEADER, QUICKCHG}
C_WRITES = {FULL_BQ, QUICKCHG}


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


def source_contract(route):
    c = json.loads((route / 'SOURCE-CONTRACT.json').read_text())
    require(c.get('schema') == 1 and c.get('source_commit') == BASE_COMMIT and
            c.get('preparation_parent_contract_sha256') == PARENT_SHA and
            c.get('parent_source_contract_sha256') == PARENT_SOURCE_SHA, 'Wrong R86 source ancestry')
    require(c.get('review_status') == 'FROZEN_REVIEWED_SOURCE' and
            len(c.get('writes', [])) == 3 and {r['path'] for r in c['writes']} == WRITES,
            'Only the frozen BQ source/header and quickchg source may change')
    require(c.get('compile_only') is True and c.get('full_charging_control_enabled') is False and
            c.get('activation_allowed') is False, 'Inactive compile proof required')
    require(len(c.get('patches', [])) == 1 and c['patches'][0]['file'] == 'patches/fastcharge-state.patch' and
            c['patches'][0]['working_directory'] == 'vendor/qcom/sm8850', 'Exactly one R86 patch at fixed root')
    guards = c.get('read_only_guards', [])
    names = [r['path'] for r in guards]
    require(len(names) == len(set(names)) and not WRITES.intersection(names), 'Overlapping source guards')
    require(STRATEGY in names and PREFIX + 'configs/canoe_perf.bzl' in names and
            PREFIX + 'drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h' in names,
            'Unchanged provider ABI, strategy and source config must be pinned')
    return c


def apply(workspace, route, verify=False):
    workspace, route = Path(workspace).resolve(), Path(route).resolve()
    c = source_contract(route)
    for row in c['read_only_guards']:
        require(pin(safe(workspace, row['path']).read_bytes()) == row['expected'],
                'Source guard changed: ' + row['path'])
    for row in c['writes']:
        require(pin(safe(workspace, row['path']).read_bytes()) == row['after' if verify else 'before'],
                'Wrong source ' + ('postimage: ' if verify else 'preimage: ') + row['path'])
    patch = c['patches'][0]
    source = safe(route, patch['file'])
    require(pin(source.read_bytes()) == {k: patch[k] for k in ('bytes', 'sha256')}, 'Patch bytes changed')
    headers = [line.split(b'\t', 1)[0] for line in source.read_bytes().splitlines()
               if line.startswith((b'--- ', b'+++ '))]
    expected = [prefix + name.removeprefix(PREFIX).encode() for name in sorted(WRITES)
                for prefix in (b'--- a/', b'+++ b/')]
    require(headers == expected, 'Patch may address only the three declared sources')
    if not verify:
        command = ['patch', '--batch', '--fuzz=0', '--forward', '-p1', '-i', str(source)]
        cwd = safe(workspace, patch['working_directory'])
        subprocess.run(command + ['--dry-run'], cwd=cwd, check=True, text=True, capture_output=True)
        subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True)
        apply(workspace, route, verify=True)
    return {'schema': 1, 'status': 'PASS_R86_EXACT_POSTIMAGES' if verify else 'PASS_R86_EXACT_OVERLAY',
            'source_commit': BASE_COMMIT, 'writes': c['writes'], 'compile_only': True,
            'activation_allowed': False, 'full_charging_control_enabled': False, 'hardware_tested': False}
