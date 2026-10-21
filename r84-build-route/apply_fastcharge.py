#!/usr/bin/env python3
"""Apply exact R84 overlays only after the frozen R83 preparation."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

BASE_COMMIT = 'c010de24a9f4a738ea4aa088ce4aa45f68ac3e09'
WRITES = {'vendor/qcom/sm8850/drivers/iio/adc/qcom-spmi-adc5-gen3.c',
          'vendor/qcom/sm8850/drivers/power/supply/myron_bq_readonly.c',
          'vendor/qcom/sm8850/drivers/power/supply/mca/mca_business/business_charger/mca_charger_usb_psy.c'}


def require(ok, why):
    if not ok:
        raise ValueError(why)


def pin(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def safe(root, relative):
    root = Path(root).resolve()
    name = PurePosixPath(relative)
    require(relative and not name.is_absolute() and '..' not in name.parts, 'Unsafe path')
    p = root / name
    require(not p.is_symlink() and p.resolve().is_relative_to(root), 'Redirected path: ' + relative)
    return p


def source_contract(route):
    c = json.loads((route / 'SOURCE-CONTRACT.json').read_text())
    require(c.get('schema') == 1 and c.get('source_commit') == BASE_COMMIT, 'Wrong source base')
    require(len(c.get('writes', [])) == 3 and {r['path'] for r in c['writes']} == WRITES,
            'Only reviewed ADC, readonly gauge and inactive USB callbacks may change')
    require(c.get('full_charging_control_enabled') is False, 'Full charging controls must stay inactive')
    return c


def apply(workspace, route, verify=False):
    workspace, route = Path(workspace).resolve(), Path(route).resolve()
    c = source_contract(route)
    for row in c['read_only_guards']:
        require(pin(safe(workspace, row['path']).read_bytes()) == row['expected'], 'Source guard changed: ' + row['path'])
    for row in c['writes']:
        require(pin(safe(workspace, row['path']).read_bytes()) == row['after' if verify else 'before'], 'Wrong source ' + ('postimage: ' if verify else 'preimage: ') + row['path'])
    for patch in c['patches']:
        f = safe(route, patch['file'])
        require(pin(f.read_bytes()) == {k: patch[k] for k in ('bytes', 'sha256')}, 'Patch bytes changed')
        if not verify:
            cwd = safe(workspace, patch['working_directory'])
            command = ['patch', '--batch', '--fuzz=0', '--forward', '-p1', '-i', str(f)]
            subprocess.run(command + ['--dry-run'], cwd=cwd, check=True, text=True, capture_output=True)
            subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True)
    if not verify:
        apply(workspace, route, verify=True)
    return {'schema': 1, 'status': 'PASS_R84_EXACT_POSTIMAGES' if verify else 'PASS_R84_EXACT_OVERLAYS',
            'source_commit': BASE_COMMIT, 'writes': c['writes'], 'full_charging_control_enabled': False,
            'hardware_tested': False}
