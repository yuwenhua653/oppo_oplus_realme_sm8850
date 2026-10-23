#!/usr/bin/env python3
"""Execute the exact prepared R88 FG sources with injected policy failures."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from apply_fg_policy import (FG_HEADER, SOC, STRATEGY, apply, pin, require, safe, source_contract)
from inherit import reconstruct_r87


def reconstruct_inputs(repo, workspace, contract):
    reconstruct_r87(repo, workspace)
    for row in contract['read_only_guards']:
        require(pin(safe(workspace, row['path']).read_bytes()) == row['expected'],
                'Wrong offline R88 guard: ' + row['path'])
    for row in contract['writes']:
        require(pin(safe(workspace, row['path']).read_bytes()) == row['before'], 'Wrong R87 preimage')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    route = Path(__file__).resolve().parent
    repo = route.parent
    contract = source_contract(route)
    tests = json.loads((route / 'TEST-CONTRACT.json').read_text())
    require(tests.get('schema') == 1 and tests.get('review_status') == 'FROZEN_REVIEWED_SOURCE' and
            len(tests.get('jobs', [])) == 1 and tests['jobs'][0]['name'] == 'fg_policy',
            'Exact FG policy production suite required')
    output = args.output.resolve()
    require(not output.exists() and not output.is_symlink(), 'Fresh production test output required')
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='r88-production-tests-') as temporary:
        before = Path(temporary) / 'before'
        before.mkdir()
        reconstruct_inputs(repo, before, contract)
        if args.workspace:
            workspace = args.workspace.resolve()
            apply(workspace, route, verify=True)
        else:
            workspace = Path(temporary) / 'after'
            workspace.mkdir()
            reconstruct_inputs(repo, workspace, contract)
            apply(workspace, route)
        names = {'strategy': STRATEGY, 'strategy_header': FG_HEADER, 'soc_smooth': SOC}
        replacements = {name: str(safe(workspace, path)) for name, path in names.items()}
        replacements.update({'before_strategy': str(safe(before, STRATEGY)),
                             'before_soc_smooth': str(safe(before, SOC))})
        reports = []
        for job in tests['jobs']:
            require(isinstance(job.get('arguments'), list) and all(isinstance(a, str) for a in job['arguments']),
                    'Explicit production test arguments required')
            command = [sys.executable, '-B', str(safe(route, job['script']))] + [
                a.format(**dict(replacements, output=str(output / job['name']))) for a in job['arguments']]
            result = subprocess.run(command, capture_output=True, text=True)
            (output / (job['name'] + '.log')).write_text(result.stdout + result.stderr)
            require(result.returncode == 0, job['name'] + ' production C failed: ' + result.stdout + result.stderr)
            reports.append({'name': job['name'], 'script': job['script'],
                            'script_pin': pin(safe(route, job['script']).read_bytes()), 'returncode': result.returncode})
        record = {'schema': 1, 'status': 'PASS_R88_COMPOSED_PRODUCTION_SOURCES',
                  'actual_prepared_workspace': bool(args.workspace), 'tests': reports,
                  'sources': {row['path']: pin(safe(workspace, row['path']).read_bytes()) for row in contract['writes']},
                  'target_compile_tested': False, 'hardware_tested': False}
        (output / 'RESULT.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
        print(json.dumps({'status': record['status'], 'tests': [r['name'] for r in reports]}))


if __name__ == '__main__':
    main()
