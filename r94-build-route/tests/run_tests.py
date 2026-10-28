#!/usr/bin/env python3
"""Execute actual LED budget functions with host faults; no phone/kernel claim."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROUTE = HERE.parent
PREIMAGE_SHA = '84fd44ce4b6170066b82eeb082b634e6e051a412f736760cf76ec42c33017766'


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def function(source, name):
    # Exact declaration and balanced braces, never a hand-copied implementation.
    pattern = re.compile(r'^static (?:int|bool)\s+' + re.escape(name) + r'\s*\(', re.M)
    matches = list(pattern.finditer(source))
    require(len(matches) == 1, 'Missing/duplicate C function ' + name)
    start = matches[0].start()
    opening = source.index('{', matches[0].end())
    depth = 1
    pos = opening + 1
    while depth:
        require(pos < len(source), 'Unterminated function ' + name)
        depth += (source[pos] == '{') - (source[pos] == '}')
        pos += 1
    return source[start:pos] + '\n'


def inspect_unchanged(old, source):
    names = [
        'set_flash_module_en', 'set_lmh_mitigation', 'update_allowed_flash_current',
        'set_flash_current', 'set_flash_timeout', 'set_flash_strobe',
        'qcom_flash_brightness_set', 'qcom_flash_timeout_set',
        'qcom_flash_strobe_set', 'qcom_flash_strobe_get', 'qcom_flash_fault_get',
        'qcom_flash_led_brightness_set', 'qcom_flash_get_iio_chan',
        'qcom_flash_iio_getprop', 'qcom_flash_led_voltage_headroom_get',
        'qcom_flash_register_led_device',
    ]
    for name in names:
        require(function(old, name) == function(source, name),
                'An unrelated hardware/protection path changed: ' + name)
    begin = '/* Battery power supply returns -ve value for discharging */'
    end = '\n\t*max_current_ma = min(MAX_FLASH_CURRENT_MA,'
    before_formula = old[old.index(begin):old.index(end, old.index(begin))]
    after_formula = source[source.index(begin):source.index(
        '\n\t/* Never let a depleted/overloaded budget wrap', source.index(begin))]
    require(before_formula == after_formula, 'Current sign or dynamic budget formula changed')
    constants = old[old.index('#define MAX_FLASH_CURRENT_MA'):old.index('static int qcom_flash_get_iio_chan')]
    require(constants in source, 'Current/voltage protection constants changed')
    return names, constants


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROUTE/'payload/leds-qcom-flash.c')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    old_bytes = (ROUTE/'preimage/leds-qcom-flash.c').read_bytes()
    require(digest(old_bytes) == PREIMAGE_SHA, 'Unpinned preimage')
    data = args.source.read_bytes()
    old, source = old_bytes.decode(), data.decode()
    protected, constants = inspect_unchanged(old, source)
    fixed_model = re.search(r'^#define MYRON_MCA_RBATT_MODEL_UOHM\s+\d+\s*$', source, re.M)
    require(fixed_model is not None, 'OEM model define missing')
    generated = (HERE/'host_shim.h').read_text() + '\n' + constants + '\n' + fixed_model.group(0) + '\n'
    for name in ['qcom_flash_led_voltage_headroom_get', 'qcom_flash_is_pmh0101',
                 'qcom_flash_uses_mca_model', '__qcom_flash_led_get_max_avail_current']:
        generated += function(source, name) + '\n'
    generated += function(old, '__qcom_flash_led_get_max_avail_current').replace(
        '__qcom_flash_led_get_max_avail_current(', 'original_get_max(', 1) + '\n'
    generated += (HERE/'host_cases.c').read_text()
    cc = shutil.which(os.environ.get('CC', 'cc'))
    require(cc, 'A host C compiler is required')
    with tempfile.TemporaryDirectory(prefix='r94-flash-test-') as tmp:
        tmp = Path(tmp)
        cfile, binary = tmp/'extracted-budget.c', tmp/'budget-tests'
        cfile.write_text(generated)
        command = [cc, '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                   '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                   '-fno-omit-frame-pointer', str(cfile), '-o', str(binary)]
        subprocess.run(command, check=True, capture_output=True, text=True)
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:abort_on_error=1',
                   UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
        result = subprocess.run([str(binary)], capture_output=True, text=True, env=env)
        require(result.returncode == 0, 'C harness failed: ' + result.stdout + result.stderr)
        observed = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        require(observed.get('status') == 'PASS', 'C harness did not finish')
        report = {
            'schema': 1, 'status': 'PASS_ACTUAL_FLASH_FUNCTION_HOST_TESTS',
            'source_sha256': digest(data), 'preimage_sha256': digest(old_bytes),
            'extracted_translation_unit_sha256': digest(generated.encode()),
            'test_sources': {p.name: digest(p.read_bytes()) for p in
                             [HERE/'run_tests.py', HERE/'host_cases.c', HERE/'host_shim.h']},
            'compiler': subprocess.check_output([cc, '--version'], text=True).splitlines()[0],
            'flags': command[1:-3],
            'asan_leak_detection': False,
            'asan_leak_detection_reason': 'This host restricts /proc task reads; extracted functions and mocks do not allocate memory.',
            'assertions': int(observed['assertions']),
            'grid_comparisons': int(observed['grid_comparisons']),
            'byte_identical_protection_functions': protected,
            'formula_and_constants_unchanged': True,
            'failure_output_unchanged': True,
            'hardware_tested': False, 'kernel_compiled': False,
            'limitations': [
                'Host mocks verify selection, error propagation and real C budget arithmetic; not Android hardware.',
                'Numerical grid: 2.5-4.6 V, CURRENT_NOW -10 A through +4.5 A, all three existing hardware branches.',
                'Does not assert safe arithmetic for arbitrary corrupted int32 inputs; inherited INT_MIN/overflow behavior is outside this bounded grid.',
            ],
        }
        if args.out:
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out/'actual-budget-host-tests.json').write_text(json.dumps(report, indent=2)+'\n')
            (args.out/'actual-budget-host-tests.log').write_text(result.stdout+result.stderr)
            (args.out/'extracted-budget.c').write_text(generated)
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
