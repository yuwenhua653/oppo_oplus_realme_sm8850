#!/usr/bin/env python3
"""Test real R88 native guards using a non-activatable known R87 data fixture.

No R88 runtime contract, module insertion or image is produced. A synthetic
RUNTIME_FROZEN=0 header preserves the old fixture's exact module pins while
moving only helper identity and fixed addition paths to the new R88 namespace.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from generate_contract import make_header

FIXTURE_SHA = 'dbadde7207b4c976e5c203f5d4512b8d623da48f96755744b0c5bf31643e355b'


def pin(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture-contract', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    raw = args.fixture_contract.read_bytes()
    if pin(raw)['sha256'] != FIXTURE_SHA or args.out.exists():
        raise ValueError('Exact known R87 test fixture and fresh output required')
    contract = json.loads(raw)
    contract.update(build_id='R88-NATIVE-UNIT-TEST-DRAFT', runtime_frozen=False,
                    activation_allowed=False, review_status='DRAFT_NOT_FOR_RUNTIME')
    for row in contract['additions']:
        if not row['path'].startswith('/vendor_dlkm/r32/r87-mca/'):
            raise ValueError('Unexpected fixture path')
        row['path'] = row['path'].replace('/r87-mca/', '/r88-mca/')
    test_data = (json.dumps(contract, sort_keys=True) + '\n').encode()
    args.out.mkdir(parents=True)
    source = Path(__file__).resolve().parent / 'native'
    for name in ('mca_start.c', 'sha256_fixed.h', 'test_mca_start.c'):
        shutil.copy2(source / name, args.out / name)
    (args.out / 'mca_contract.h').write_text(make_header(contract, pin(test_data)['sha256']))
    binary = args.out.resolve() / 'host-tests'
    command = ['cc', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
               '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-no-pie',
               '-o', str(binary), str((args.out / 'test_mca_start.c').resolve())]
    subprocess.run(command, check=True, capture_output=True, text=True)
    result = subprocess.run([str(binary)], check=True, capture_output=True, text=True, env={
        **os.environ, 'ASAN_OPTIONS': 'detect_leaks=0:abort_on_error=1',
        'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'})
    (args.out / 'HOST-TESTS.txt').write_text(result.stdout + result.stderr)
    report = {'schema': 1, 'status': 'PASS_NATIVE_GUARDS_NONACTIVATABLE_FIXTURE_ONLY',
              'fixture_source': 'Exact historical R87 module-set; only unit test data', 'fixture': pin(raw),
              'production_c': pin((source / 'mca_start.c').read_bytes()),
              'test_c': pin((source / 'test_mca_start.c').read_bytes()),
              'runtime_frozen': False, 'activation_allowed': False, 'image_created': False,
              'hardware_tested': False, 'ASan_UBSan_Werror': True, 'output': result.stdout.strip()}
    (args.out / 'GUARD-TEST-REVIEW.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
