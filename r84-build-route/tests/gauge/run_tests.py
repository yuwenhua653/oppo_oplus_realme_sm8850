#!/usr/bin/env python3
"""Compile the complete independent gauge against bounded kernel API mocks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
source = args.source.resolve()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=False)
text = source.read_text()
headers = re.findall(r'^#include\s+<([^>]+)>', text, re.M)
assert len(headers) == 14 and all(h.startswith('linux/') for h in headers)
assert not re.search(r'^#include\s+"', text, re.M)
assert 'MODULE_DEVICE_TABLE' not in text
assert dict(re.findall(r'#define (MYRON_REG_[A-Z_]+)\s+(0x[0-9a-f]+)', text)) == {
    'MYRON_REG_SOC': '0x2c', 'MYRON_REG_VOLTAGE': '0x08',
    'MYRON_REG_TEMPERATURE': '0x06', 'MYRON_REG_BATTERY_STATUS': '0x0a',
    'MYRON_REG_CURRENT': '0x0c',
}
code = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
assert len(re.findall(r'i2c_smbus_read_word_data\(', code)) == 4
assert len(re.findall(r'i2c_transfer\(', code)) == 2
assert len(re.findall(r'usleep_range\(', code)) == 1
assert len(re.findall(r'\.no_thermal\s*=\s*false', code)) == 3
for forbidden in (
    'i2c_smbus_write', 'i2c_master_send', 'i2c_new',
    'device_release_driver', 'device_bind_driver', 'driver_override',
    'schedule_work', 'queue_delayed_work', 'set_property',
    'property_is_writeable', 'POWER_SUPPLY_PROP_PRESENT',
    'POWER_SUPPLY_PROP_ONLINE', 'i2c_smbus_read_byte',
    'i2c_smbus_read_i2c_block', 'pmic_glink', 'EXPORT_SYMBOL',
):
    assert forbidden not in code, forbidden
for option in ('enable_readonly', 'enable_extended_readonly', 'enable_status_readonly', 'enable_manufacturer_query'):
    assert f'static bool {option};' in code
    assert f'module_param({option}, bool, 0444);' in code
assert not re.search(r'\.shutdown\s*=|\.pm\s*=', code)
assert len(re.findall(r'\.remove\s*=\s*myron_readonly_remove,', code)) == 1
assert len(re.findall(r'\.external_power_changed\s*=', code)) == 1
assert len(re.findall(r'power_supply_get_property\(', code)) == 2
assert 'usb->dev.parent' not in code

stubs = out / 'stubs'
for header in headers:
    path = stubs / header
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('#include "fake_kernel.h"\n')
(out / 'production_under_test.c').write_bytes(source.read_bytes())
cc = shutil.which('gcc')
assert cc
flags = [
    '-std=gnu11', '-g', '-O1', '-pthread', '-Wall', '-Wextra', '-Werror',
    '-Wno-unused-parameter', '-Wno-unused-function', '-Wno-misleading-indentation',
    '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-no-pie',
]
cmd = [cc, *flags, '-I' + str(stubs), '-I' + str(HERE), '-I' + str(out),
       str(HERE / 'test_gauge.c'), '-o', str(out / 'test_gauge')]
build = subprocess.run(cmd, text=True, capture_output=True)
(out / 'compile.log').write_text(build.stdout + build.stderr)
if build.returncode:
    print(build.stdout + build.stderr)
    raise SystemExit(build.returncode)
run = subprocess.run(
    [str(out / 'test_gauge')], text=True, capture_output=True, timeout=30,
    env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0:abort_on_error=1',
             UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1'),
)
(out / 'run.log').write_text(run.stdout + run.stderr)
count = len(re.findall(r'^PASS ', run.stdout, re.M))
passed = run.returncode == 0 and count >= 74
report = {
    'status': 'PASS' if passed else 'FAIL',
    'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'actual_whole_production_translation_unit': True,
    'host_fixture_groups': count,
    'original_fixture_groups_retained': 60, 'new_manufacturer_groups': 14,
    'sanitizers': ['address', 'undefined'],
    'compiler': subprocess.check_output([cc, '--version'], text=True).splitlines()[0],
    'flags': flags, 'exit_code': run.returncode,
    'stdout': run.stdout, 'stderr': run.stderr,
    'uses_old_driver_source_or_headers': False,
    'limits': [
        'Host API mocks with pthread-backed PSY device locks; not target kernel/hardware validation.',
        'Two deterministic concurrent schedules exercise supplier read/removal and consumer event/removal barriers.',
        'No TSan or lockdep. LeakSanitizer disabled; explicit reference/devres assertions retained.',
        'Provider cache freshness is modeled by error returns and is tested in the separate production client suite.',
    ],
}
(out / 'RESULT.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
raise SystemExit(0 if passed else 1)
