#!/usr/bin/env python3
"""Apply only the reviewed charging error repairs over successful R86."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

BASE_COMMIT = '96f969059c9fb2ccfbf2f5ac83e1f864770da21c'
PARENT = 'r86-build-route/build-contract.json'
PARENT_SHA = 'd0bd66b09c1d836a532eb1c1b9b9356108ffe8e964a046170239e3012be2c843'
PARENT_SOURCE_SHA = 'dfc42164a431a8510aa36addcc017651847e01c915bd074097dd72b98c062f84'
PREFIX = 'vendor/qcom/sm8850/'
CP = PREFIX + 'drivers/power/supply/mca/mca_hardware_ic/charge_pump_ic/sc8581/sc8581.c'
FULL_BQ = PREFIX + 'drivers/power/supply/mca/mca_hardware_ic/fuelgauge_ic/bq27z561/bq27z561.c'
HEADER = PREFIX + 'drivers/power/supply/mca/mca_hardware_ic/fuelgauge_ic/bq27z561/inc/bq27z561.h'
QUICKCHG = PREFIX + 'drivers/power/supply/mca/mca_strategy/strategy_charger/mca_strategy_quickchg.c'
STRATEGY = PREFIX + 'drivers/power/supply/mca/mca_strategy/strategy_fg/mca_strategy_fg.c'
FG_HEADER = PREFIX + 'drivers/power/supply/mca/mca_strategy/strategy_fg/inc/strategy_fg.h'
GLINK = PREFIX + 'drivers/power/supply/mca/mca_common/mca_adsp_glink.c'
SUBPMIC = PREFIX + 'drivers/power/supply/mca/mca_qcom_subpmic_proxy/mca_qcom_subpmic_proxy.c'
USB = PREFIX + 'drivers/power/supply/mca/mca_business/business_charger/mca_charger_usb_psy.c'
WRITES = {CP, QUICKCHG}


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
            c.get('parent_source_contract_sha256') == PARENT_SOURCE_SHA, 'Wrong R87 source ancestry')
    require(c.get('review_status') == 'FROZEN_REVIEWED_SOURCE' and
            len(c.get('writes', [])) == 2 and {r['path'] for r in c['writes']} == WRITES,
            'Only reviewed CP and quickchg sources may change')
    require(c.get('compile_only') is True and c.get('activation_allowed') is False and
            c.get('full_charging_control_enabled') is False, 'Inactive compile proof required')
    require(len(c.get('patches', [])) == 1 and c['patches'][0]['file'] == 'patches/charging-error-safety.patch' and
            c['patches'][0]['working_directory'] == 'vendor/qcom/sm8850', 'One exact charging error patch required')
    guards = c.get('read_only_guards', [])
    names = [r['path'] for r in guards]
    require(len(names) == len(set(names)) and not WRITES.intersection(names), 'Overlapping source guards')
    require({FULL_BQ, HEADER, USB, STRATEGY, FG_HEADER, GLINK, SUBPMIC,
             PREFIX + 'configs/canoe_perf.bzl',
             PREFIX + 'drivers/power/supply/mca/include/mca/platform/platform_fg_ic_ops.h'} <= set(names),
            'R86 BQ/strategy, inherited full-MCA power sources and source config must stay pinned')
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
    require(headers == expected, 'Patch may change only the two declared charging sources')
    if not verify:
        command = ['patch', '--batch', '--fuzz=0', '--forward', '-p1', '-i', str(source)]
        cwd = safe(workspace, patch['working_directory'])
        subprocess.run(command + ['--dry-run'], cwd=cwd, check=True, capture_output=True)
        subprocess.run(command, cwd=cwd, check=True, capture_output=True)
        apply(workspace, route, verify=True)
    return {'schema': 1, 'status': 'PASS_R87_EXACT_POSTIMAGES' if verify else 'PASS_R87_EXACT_OVERLAY',
            'source_commit': BASE_COMMIT, 'writes': c['writes'], 'compile_only': True,
            'activation_allowed': False, 'full_charging_control_enabled': False, 'hardware_tested': False}
