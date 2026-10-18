#!/usr/bin/env python3
"""Compile and test exact extracted production functions without kernel hardware.

No copied or rewritten control implementation is present in the harnesses.
The source root is configurable to demonstrate that unchanged preimages fail.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PROXY = Path('drivers/power/supply/mca/mca_qcom_subpmic_proxy/mca_qcom_subpmic_proxy.c')
BUCK = Path('drivers/power/supply/mca/mca_strategy/strategy_charger/mca_strategy_buckchg.c')
SETTERS = ('qcom_subpmic_set_charge_current', 'qcom_subpmic_enable_charging',
           'qcom_subpmic_set_term_volt', 'qcom_subpmic_set_input_current_limit')


def extract_function(source, name):
    match = re.search(r'^static int ' + re.escape(name) + r'\(', source, re.M)
    if not match:
        raise ValueError('Production function not found: ' + name)
    opening = source.index('{', match.start())
    depth = 0
    for index in range(opening, len(source)):
        depth += (source[index] == '{') - (source[index] == '}')
        if depth == 0:
            return source[match.start():index + 1]
    raise ValueError('Unterminated function: ' + name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, default=ROOT / 'payload')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    proxy, buck = (source_root / PROXY).read_text(), (source_root / BUCK).read_text()
    enum = re.search(r'^enum mca_subpmic_prop \{.*?^\};', proxy, re.M | re.S).group(0)
    functions = {name: extract_function(proxy, name) for name in SETTERS}
    functions['strategy_buckchg_class_probe'] = extract_function(buck, 'strategy_buckchg_class_probe')
    suites = {
        'setters': enum + '\n' + '\n'.join(functions[name] for name in SETTERS),
        'probe': functions['strategy_buckchg_class_probe'],
    }
    report = {'schema': 1, 'source_root': str(source_root), 'source_files': [
        {'path': str(path), 'sha256': hashlib.sha256((source_root / path).read_bytes()).hexdigest()}
        for path in (PROXY, BUCK)], 'function_sha256': {
        name: hashlib.sha256(body.encode()).hexdigest() for name, body in functions.items()},
        'method': 'Host C tests compile full exact production functions with instrumented dependency stubs.',
        'limitations': ['Not an in-kernel, firmware or hardware test.',
                       'No claim of full charging safety, dependency closure or late-probe lifecycle safety.'],
        'suites': {}}
    with tempfile.TemporaryDirectory(prefix='r76-control-extracted-') as directory:
        directory = Path(directory)
        for name, body in suites.items():
            harness = (Path(__file__).resolve().parent / (name + '_harness.c')).read_text()
            assert harness.count('/* PRODUCTION_FUNCTIONS */') == 1
            source = directory / (name + '.c')
            source.write_text(harness.replace('/* PRODUCTION_FUNCTIONS */', body))
            binary = directory / name
            compiled = subprocess.run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Wstrict-prototypes',
                                       '-Werror', '-Wno-unused-value', '-Wno-unused-parameter',
                                       '-Wno-error=maybe-uninitialized', str(source), '-o', str(binary)],
                                      text=True, capture_output=True)
            compile_stderr = compiled.stderr.replace(str(directory), '<extracted-test>')
            if compiled.returncode:
                report['suites'][name] = {'pass': False, 'phase': 'compile', 'stderr': compile_stderr}
                print(compile_stderr)
                continue
            run = subprocess.run([str(binary)], text=True, capture_output=True)
            report['suites'][name] = {'pass': run.returncode == 0, 'exit_code': run.returncode,
                                    'stdout': run.stdout.strip(), 'stderr': run.stderr.strip(),
                                    'compile_stderr': compile_stderr.strip()}
            print(run.stdout or run.stderr, end='')
    report['pass'] = all(suite['pass'] for suite in report['suites'].values())
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    raise SystemExit(0 if report['pass'] else 1)


if __name__ == '__main__':
    main()
