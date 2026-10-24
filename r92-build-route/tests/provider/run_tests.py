#!/usr/bin/env python3
"""Run exact provider C against stock-wire fixtures; mocks never access hardware."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--source', required=True, type=Path)
p.add_argument('--out', required=True, type=Path)
a = p.parse_args()
r = Path(__file__).resolve().parent
a.out.mkdir(parents=True, exist_ok=True)
source = a.source.resolve()
compiler = shutil.which('clang') or shutil.which('cc')
assert compiler, 'a C compiler is required'
flags = ['-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
         '-Wno-unused-parameter', '-Wno-unused-function', '-Wno-unused-variable',
         '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
         '-I', str(r / 'include')]
results = []
for negative, src in [(False, source), (True, r / 'preimage.c')]:
    name = 'preimage-negative' if negative else 'provider'
    binary = (a.out / name).resolve()
    cmd = [compiler, *flags, f'-DSOURCE_PATH="{src}"']
    if negative:
        cmd += ['-DNEGATIVE_CONTROL']
    cmd += [str(r / 'harness.c'), '-o', str(binary)]
    built = subprocess.run(cmd, capture_output=True, text=True)
    (a.out / f'{name}-compile.log').write_text(built.stdout + built.stderr)
    assert built.returncode == 0, built.stderr
    run = subprocess.run([str(binary)], capture_output=True, text=True,
                         env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0'})
    (a.out / f'{name}-run.log').write_text(run.stdout + run.stderr)
    if negative:
        assert run.returncode != 0 and 'wire mismatch actual=W/0x21017/4 expected=W/0x21018/4' in run.stderr, run.stdout + run.stderr
    else:
        assert run.returncode == 0, run.stdout + run.stderr
    results.append({'case': name, 'returncode': run.returncode, 'expected_failure': negative})
# Prevent reintroducing auth payload formatting in this provider's log calls.
s = source.read_text()
for log in re.findall(r'(?:mca_log_(?:info|err)|pr_info)\s*\(.*?\);', s, re.S):
    assert not re.search(r'\b(?:buf|vdm_data|s_secert|digest)\s*\[|\*vdm_data', log), log
report = {
    'status': 'PASS', 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
    'preimage_sha256': hashlib.sha256((r / 'preimage.c').read_bytes()).hexdigest(),
    'compiler': compiler, 'sanitizers': ['address', 'undefined'],
    'leak_sanitizer': 'disabled because execution environment restricts /proc task access',
    'scope': 'full production C compiled with isolated kernel/GLINK mocks; not a kernel build or phone fast-charge result',
    'checks': ['stock IDs and wire sizes for all enabled provider transactions',
               'PPS voltage/current packing and status decoding',
               '7 x 16-byte PDO records and invalid count rejection',
               'transport error propagation and failed auth response output preservation',
               'verified/support cache and disconnect invalidation',
               'disconnect/GLINK-down injected during verified write and keep-PDO read cannot restore stale cache',
               'failed clear-verified write preserves prior state; verify-process failure preserves inherited stock cache behavior',
               'VDM 0/1/3/4/15-byte rejection with ASan and 16-byte byte swap',
               'notifier registration failure unwind and remove cleanup',
               'diagnostic reads perform zero GLINK transactions',
               'exact preimage fails at old PPS selection property'],
    'results': results,
}
(a.out / 'HOST-PROVIDER-TESTS.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
