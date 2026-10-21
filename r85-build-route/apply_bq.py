#!/usr/bin/env python3
"""Apply only the reviewed full-BQ safety overlay after frozen R84 preparation."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

BASE_COMMIT = '5e4568f2ff6ed8257a3c9f5974605cafab8e956a'
PARENT_SHA = '1bea452ed2f1a337b5c6e588251bdb24b816a22248fe1dde956e05fc01898eec'
FULL_BQ = 'vendor/qcom/sm8850/drivers/power/supply/mca/mca_hardware_ic/fuelgauge_ic/bq27z561/bq27z561.c'
HEADER = 'vendor/qcom/sm8850/drivers/power/supply/mca/mca_hardware_ic/fuelgauge_ic/bq27z561/inc/bq27z561.h'
WRITES = {FULL_BQ}


def require(ok, why):
    if not ok:
        raise ValueError(why)


def pin(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def safe(root, relative):
    root = Path(root).resolve()
    name = PurePosixPath(relative)
    require(relative and not name.is_absolute() and '..' not in name.parts,
            'Unsafe relative path')
    target = root / name
    require(target.resolve().is_relative_to(root), 'Escaping path: ' + relative)
    require(all(not (root / Path(*name.parts[:i])).is_symlink()
                for i in range(1, len(name.parts) + 1)), 'Symlink path: ' + relative)
    return target


def source_contract(route):
    c = json.loads((route / 'SOURCE-CONTRACT.json').read_text())
    require(c.get('schema') == 1 and c.get('source_commit') == BASE_COMMIT and
            c.get('preparation_parent_contract_sha256') == PARENT_SHA,
            'Wrong R85 source ancestry')
    require(c.get('review_status') == 'FROZEN_REVIEWED_SOURCE' and
            len(c.get('writes', [])) == 1 and {r['path'] for r in c['writes']} == WRITES,
            'Only the frozen reviewed full-BQ source may change')
    require(c.get('compile_only') is True and c.get('full_charging_control_enabled') is False and
            c.get('activation_allowed') is False, 'Inactive compile proof required')
    require(len(c.get('patches', [])) == 1 and
            c['patches'][0]['file'] == 'patches/bq-full-safety.patch' and
            c['patches'][0]['working_directory'] == 'vendor/qcom/sm8850',
            'Exactly one full-BQ patch at the fixed source root')
    guards = c.get('read_only_guards', [])
    names = [r['path'] for r in guards]
    require(len(names) == len(set(names)) and not WRITES.intersection(names),
            'Duplicate or overlapping source guards')
    require(c.get('header_path') == HEADER and HEADER in names,
            'The unchanged full-BQ header must be pinned')
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
    require(pin(source.read_bytes()) == {k: patch[k] for k in ('bytes', 'sha256')},
            'Patch bytes changed')
    relative = FULL_BQ.removeprefix('vendor/qcom/sm8850/')
    headers = [line.split(b'\t', 1)[0] for line in source.read_bytes().splitlines()
               if line.startswith((b'--- ', b'+++ '))]
    require(headers == [b'--- a/' + relative.encode(), b'+++ b/' + relative.encode()],
            'Patch may address only the one full-BQ source')
    if not verify:
        command = ['patch', '--batch', '--fuzz=0', '--forward', '-p1', '-i', str(source)]
        cwd = safe(workspace, patch['working_directory'])
        subprocess.run(command + ['--dry-run'], cwd=cwd, check=True, text=True, capture_output=True)
        subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True)
        apply(workspace, route, verify=True)
    return {'schema': 1, 'status': 'PASS_R85_EXACT_POSTIMAGES' if verify else 'PASS_R85_EXACT_OVERLAY',
            'source_commit': BASE_COMMIT, 'writes': c['writes'], 'compile_only': True,
            'activation_allowed': False, 'full_charging_control_enabled': False,
            'hardware_tested': False}
