#!/usr/bin/env python3
"""Run R89 production metadata/probe tests and retained charging-control tests."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from apply_probe_recovery import BQ, QUICK, apply, pin, require, safe, source_contract


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    root, output = args.workspace.resolve(), args.output.resolve()
    route = Path(__file__).resolve().parent
    repo = route.parent
    contract = source_contract(route)
    apply(root, route, verify=True)
    require(not output.exists() and not output.is_symlink(), 'Fresh R89 test output required')
    output.mkdir(parents=True)
    before_bq = route / 'preimage/bq27z561.c'
    before_quick = route / 'preimage/mca_strategy_quickchg.c'
    before = {BQ: before_bq, QUICK: before_quick}
    for row in contract['writes']:
        require(pin(before[row['path']].read_bytes()) == row['before'], 'Wrong R88 negative-control source')
    prefix = 'vendor/qcom/sm8850/drivers/power/supply/mca/'
    jobs = [
        ('bq_metadata', route / 'tests/bq_metadata/test_source.py', [
            '--source', str(safe(root, BQ)), '--before', str(before_bq),
            '--header', str(safe(root, prefix + 'mca_hardware_ic/fuelgauge_ic/bq27z561/inc/bq27z561.h')),
            '--patch', str(route / 'tests/bq_metadata/bq-cell-vendor-retry.patch')]),
        ('probe_diagnostics', route / 'tests/probe_diag/test_source.py', [
            '--source', str(safe(root, QUICK)), '--before', str(before_quick)]),
        ('retained_fastcharge_fanout', repo / 'r87-build-route/tests/fanout/run_tests.py', [
            '--quickchg', str(safe(root, QUICK)), '--bq', str(safe(root, BQ)),
            '--strategy', str(safe(root, prefix + 'mca_strategy/strategy_fg/mca_strategy_fg.c')),
            '--strategy-header', str(safe(root, prefix + 'mca_strategy/strategy_fg/inc/strategy_fg.h'))]),
    ]
    reports = []
    for name, script, arguments in jobs:
        command = [sys.executable, '-B', str(script), *arguments, '--out', str(output / name)]
        result = subprocess.run(command, text=True, capture_output=True, timeout=180)
        (output / (name + '.log')).write_text(result.stdout + result.stderr)
        require(result.returncode == 0, name + ' failed: ' + result.stdout + result.stderr)
        reports.append({'name': name, 'script': str(script.relative_to(repo)),
                        'script_pin': pin(script.read_bytes()), 'returncode': result.returncode})
    record = {'schema': 1, 'status': 'PASS_R89_PRODUCTION_SOURCE_TESTS', 'tests': reports,
              'sources': {row['path']: pin(safe(root, row['path']).read_bytes()) for row in contract['writes']},
              'target_compile_tested': False, 'hardware_tested': False,
              'limit': 'Extracted production functions with synthetic dependencies; CI performs the full kernel/module compile.'}
    (output / 'RESULT.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    print(json.dumps(record))


if __name__ == '__main__':
    main()
