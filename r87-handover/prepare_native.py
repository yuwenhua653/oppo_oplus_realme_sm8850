#!/usr/bin/env python3
"""Build the exact fixed R87 native helper and exercise production-C guards."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from generate_contract import make_header, need, pin


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--contract', type=Path, required=True)
    p.add_argument('--toolchain', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    need(not a.out.exists(), 'Fresh native output required')
    root = Path(__file__).resolve().parent
    raw = a.contract.read_bytes()
    contract = json.loads(raw)
    need(contract['schema'] == 1 and contract['normal_module_count'] == 249 and
         contract['total_module_count'] == 294 and len(contract['baseline']) == 249 and
         len(contract['additions']) == 45 and all(r['load_arguments'] == '' for r in contract['additions']),
         'Exact fixed native module set required')
    need(contract['runtime_frozen'] == contract['activation_allowed'] and
         contract['review_status'] == ('FROZEN_REVIEWED_R87_RUNTIME_CANDIDATE' if contract['runtime_frozen'] else 'DRAFT_NOT_FOR_RUNTIME'),
         'Frozen or explicitly non-activatable draft contract required')
    tc = json.loads(a.toolchain.read_text())
    for row in tc['packages']:
        need(pin(Path(row['path']).read_bytes()) == {k: row[k] for k in ('bytes', 'sha256')}, 'Frozen toolchain package changed')
    a.out.mkdir(parents=True)
    (a.out / 'module-set.json').write_bytes(raw)
    (a.out / 'mca_contract.h').write_text(make_header(contract, pin(raw)['sha256']))
    for name in ('mca_start.c', 'sha256_fixed.h', 'test_mca_start.c'):
        shutil.copy2(root / 'native' / name, a.out / name)
    env = {**os.environ, **tc['env_overrides']}
    commands = []
    def run(argv, run_env=None):
        r = subprocess.run(list(map(str, argv)), capture_output=True, text=True, env=run_env, timeout=60)
        commands.append({'argv': list(map(str, argv)), 'returncode': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr})
        need(r.returncode == 0, 'Native build/test failed: ' + r.stdout + r.stderr)
        return r
    for name in ('r87-mca-start', 'r87-mca-start-reproduction'):
        run(tc['compile_argv'] + ['-o', str((a.out / name).resolve()), str((a.out / 'mca_start.c').resolve())], env)
        run(tc['strip_argv'] + [str((a.out / name).resolve())], env)
    binary = (a.out / 'r87-mca-start').read_bytes()
    need(binary == (a.out / 'r87-mca-start-reproduction').read_bytes(), 'Deterministic native reproduction required')
    need(binary[:6] == b'\x7fELF\x02\x01' and binary[18:20] == b'\xb7\x00' and contract['build_id'].encode() in binary,
         'Actual AArch64 helper and shared identity required')
    flags = ['cc', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
             '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-no-pie',
             '-o', str((a.out / 'host-tests').resolve()), str((a.out / 'test_mca_start.c').resolve())]
    run(flags)
    host_env = {**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0:abort_on_error=1',
                'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'}
    tests = run([str((a.out / 'host-tests').resolve())], host_env)
    (a.out / 'HOST-TESTS.txt').write_text(tests.stdout + tests.stderr)
    report = {'schema': 1, 'status': 'PASS_R87_NATIVE_PREPARATION_NOT_RUNTIME_APPROVAL',
              'build_id': contract['build_id'], 'module_set': pin(raw), 'helper': pin(binary),
              'helper_source': pin((a.out / 'mca_start.c').read_bytes()),
              'generated_header': pin((a.out / 'mca_contract.h').read_bytes()),
              'host_tests_passed': True, 'host_test_output': tests.stdout.strip(), 'ASan_UBSan_Werror': True,
              'baseline_image': contract['baseline_vendor_boot'],
              'baseline_contract': {'bytes': 204254, 'sha256': contract['baseline_runtime_contract_sha256']},
              'source_ci': contract['source_ci'], 'abi_review': contract['abi_review'],
              'runtime_frozen': contract['runtime_frozen'], 'activation_allowed': contract['activation_allowed'],
              'hardware_tested': False, 'auth_success_asserted': False,
              'double_build_byte_identical': True, 'commands': commands}
    (a.out / 'PREPARE-REVIEW.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: report[k] for k in ('status', 'module_set', 'helper', 'host_test_output', 'runtime_frozen')}))


if __name__ == '__main__':
    main()
