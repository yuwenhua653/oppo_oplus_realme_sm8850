#!/usr/bin/env python3
"""Run unmodified extracted production function bodies; no kernel-build claim."""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import tempfile
from extract import function, section, span

HERE = Path(__file__).resolve().parent
MAC = ['checksum', 'fg_write_read_block', 'fg_mac_read_frame_locked',
       'fg_mac_read_block_variable', 'fg_mac_read_block']
CHANGED = ['fg_read_cell_vendor', 'fg_get_one_batt_cell_info']


def pin(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=HERE / 'after.c')
    parser.add_argument('--before', type=Path, default=HERE / 'before.c')
    parser.add_argument('--header', type=Path, default=HERE / 'reference-bq27z561.h')
    parser.add_argument('--patch', type=Path, default=HERE / 'bq-cell-vendor-retry.patch')
    parser.add_argument('--out', type=Path, default=HERE / 'test-results')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    before_bytes, after_bytes = args.before.read_bytes(), args.source.read_bytes()
    header_bytes = args.header.read_bytes()
    before, after, header = before_bytes.decode(), after_bytes.decode(), header_bytes.decode()
    # All numeric macros/enums consumed by these production bodies come from
    # the actual R88 snapshot header, rather than duplicating their definitions.
    enums = section(header, 'enum fg_cell_vendor {', '};') + '\n' + section(header, 'enum bq_fg_mac_cmd {', '};')
    bodies = {name: function(after, name) for name in MAC + CHANGED}
    # Prove there are no hidden edits outside the two permitted functions.
    normalized = after
    for name in CHANGED:
        first, last = span(normalized, name)
        normalized = normalized[:first] + function(before, name) + normalized[last:]
    assert normalized == before, 'Change exceeds metadata recovery scope'
    # Assert this scope leaves transport validation and optional probe intact.
    for name in MAC + ['bq_fg_probe']:
        assert function(before, name) == function(after, name), name
    prefix = (HERE / 'host.h').read_text() + '\n' + enums + '\n'
    combined = prefix + '\n\n'.join(bodies.values()) + '\n' + (HERE / 'cases.c').read_text()
    mock = prefix + (HERE / 'mock_cases.c').read_text().replace('/* PRODUCTION_FUNCTIONS */',
                     '\n\n'.join(bodies[name] for name in CHANGED))
    negative = '#define BEFORE_DEFECT 1\n' + prefix + (HERE / 'mock_cases.c').read_text().replace(
        '/* PRODUCTION_FUNCTIONS */', '\n\n'.join(function(before, name) for name in CHANGED))
    report = {'status': 'PASS', 'source': pin(after_bytes), 'preimage': pin(before_bytes),
        'header': pin(header_bytes), 'functions': {n: pin(b.encode()) for n,b in bodies.items()},
        'kernel_compiled': False, 'hardware_tested': False,
        'leak_check': 'disabled: runtime cannot enumerate /proc tasks for LeakSanitizer',
        'unchanged_probe_and_mac': True, 'only_two_functions_changed': True, 'commands': []}
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:abort_on_error=1',
               UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    flags = ['cc', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
             '-Wstrict-prototypes', '-Wno-unused-function', '-Wno-unused-variable',
             '-Wno-misleading-indentation', '-fsanitize=address,undefined',
             '-fno-omit-frame-pointer', '-no-pie', '-pthread', '-ftrivial-auto-var-init=pattern']
    try:
        with tempfile.TemporaryDirectory(prefix='patch-check-', dir=args.out) as temporary:
            root = Path(temporary)
            relative = 'drivers/power/supply/mca/mca_hardware_ic/fuelgauge_ic/bq27z561/bq27z561.c'
            destination = root / relative
            destination.parent.mkdir(parents=True)
            shutil.copyfile(args.before, destination)
            patch_bytes = args.patch.read_bytes()
            report['patch'] = pin(patch_bytes)
            patch_data = patch_bytes.decode()
            patch_run = subprocess.run(['patch', '--batch', '--forward', '-p1', '-d', str(root)],
                                       input=patch_data, capture_output=True, text=True, timeout=10)
            assert patch_run.returncode == 0, patch_run.stderr
            assert destination.read_bytes() == args.source.read_bytes()
            report['patch_applies_exactly'] = True
        for name,code in [('metadata_mac',combined),('direct_mac_faults',mock),('before_defect',negative)]:
            path = args.out / (name + '.c'); path.write_text(code)
            binary = args.out / name
            for command in [flags + [str(path), '-o', str(binary)], [str(binary)]]:
                p = subprocess.run(command, capture_output=True, text=True, timeout=45, env=env)
                report['commands'].append({'argv': command, 'returncode': p.returncode,
                                           'stdout': p.stdout, 'stderr': p.stderr})
                if p.returncode:
                    raise RuntimeError(p.stdout + p.stderr)
                if p.stdout:
                    print(p.stdout, end='')
    except Exception:
        report['status'] = 'FAIL'
        raise
    finally:
        (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
