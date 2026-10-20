#!/usr/bin/env python3
"""Run production-source regressions without modifying the frozen input tree."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports', type=Path, required=True)
    args = parser.parse_args()
    reports = args.reports.resolve()
    reports.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix='r79-source-tests-', dir=reports) as temp:
        work = Path(temp)
        for name in ('thermal', 'charge', 'touch', 'fg', 'display'):
            shutil.copytree(HERE / name, work / name, ignore=shutil.ignore_patterns('__pycache__'))
        commands = [
            ('integration', [sys.executable, str(HERE / 'test_integration.py')]),
            ('battery-thermal', [sys.executable, str(work / 'thermal/test_battery_thermal.py')]),
            ('gauge', [sys.executable, str(work / 'thermal/tests/gauge/run_tests.py'),
                       '--source', str(work / 'thermal/payload/drivers/power/supply/myron_bq_readonly.c'),
                       '--output', str(work / 'whole-gauge')]),
            ('subpmic-errors', [sys.executable, str(work / 'charge/test_subpmic_errors.py')]),
            ('touch', [sys.executable, str(work / 'touch/test_touch.py')]),
            ('touch-apply', [sys.executable, str(work / 'touch/test_apply.py')]),
            ('fg-errors', [sys.executable, str(work / 'fg/test_fg_errors.py')]),
            ('display', [sys.executable, str(work / 'display/tests/run_tests.py')]),
        ]
        for name, command in commands:
            result = subprocess.run(command, cwd=HERE.parent, text=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, timeout=120)
            (reports / ('r79-test-' + name + '.log')).write_text(result.stdout)
            results.append({'test': name, 'exit_code': result.returncode})
            print(name + ': ' + ('PASS' if result.returncode == 0 else 'FAIL'), flush=True)
            if result.returncode:
                print(result.stdout, file=sys.stderr)
                break
        for source, name in (
            ('thermal/BATTERY-THERMAL-TESTS.json', 'battery-thermal'),
            ('charge/TEST-RESULTS.json', 'subpmic-errors'),
            ('whole-gauge/RESULT.json', 'gauge'),
            ('touch/HOST-TESTS.json', 'touch'),
            ('touch/APPLY-TESTS.json', 'touch-apply'),
            ('fg/test-results.json', 'fg-errors'),
        ):
            path = work / source
            if path.is_file():
                shutil.copy2(path, reports / ('r79-test-' + name + '.json'))
    passed = len(results) == len(commands) and all(r['exit_code'] == 0 for r in results)
    (reports / 'r79-source-tests.json').write_text(json.dumps({'status': 'PASS' if passed else 'FAIL', 'tests': results}, indent=2) + '\n')
    return 0 if passed else 1

if __name__ == '__main__':
    sys.exit(main())
