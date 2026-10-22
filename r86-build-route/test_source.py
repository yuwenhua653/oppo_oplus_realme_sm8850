#!/usr/bin/env python3
"""Execute R86 production-C tests on exact inherited and patched source bytes."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from apply_control import FULL_BQ, HEADER, QUICKCHG, STRATEGY, PREFIX, apply, pin, require, safe, source_contract
from build_control import frozen_r85


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def reconstruct_r85(repo, workspace):
    """Reconstruct the three exact R85 preimages from their frozen source recipes."""
    r85 = frozen_r85(repo)
    r85.check(repo)
    old = r85.load('r86_parent_test_source', repo / 'r85-build-route/test_source.py')
    old.reconstruct_r84_bq(repo, workspace)
    previous = r85.source_contract(repo / 'r85-build-route')
    for guard in previous['read_only_guards']:
        data = old.offline_guard_bytes(repo, guard)
        require(pin(data) == guard['expected'], 'Wrong inherited offline guard: ' + guard['path'])
        write(safe(workspace, guard['path']), data)
    r85.apply(workspace, repo / 'r85-build-route')
    write(safe(workspace, QUICKCHG), safe(repo, 'r61-build-route/payload/' + QUICKCHG.removeprefix(PREFIX)).read_bytes())
    return old


def reconstruct_inputs(repo, workspace, contract):
    old = reconstruct_r85(repo, workspace)
    for guard in contract['read_only_guards']:
        data = old.offline_guard_bytes(repo, guard)
        require(pin(data) == guard['expected'], 'Wrong offline R86 guard: ' + guard['path'])
        write(safe(workspace, guard['path']), data)
    for row in contract['writes']:
        require(pin(safe(workspace, row['path']).read_bytes()) == row['before'], 'Wrong reconstructed R85 preimage')


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
            {j['name'] for j in tests.get('jobs', [])} == {'bq_mode', 'quickchg'} and len(tests['jobs']) == 2,
            'Exact BQ mode and quickchg production tests required')
    output = args.output.resolve()
    require(not output.exists() and not output.is_symlink(), 'Fresh production test output required')
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='r86-production-tests-') as temporary:
        before_root = Path(temporary) / 'before'
        before_root.mkdir()
        reconstruct_inputs(repo, before_root, contract)
        if args.workspace:
            workspace = args.workspace.resolve()
            apply(workspace, route, verify=True)
        else:
            workspace = Path(temporary) / 'after'
            workspace.mkdir()
            reconstruct_inputs(repo, workspace, contract)
            apply(workspace, route)
        names = {'bq': FULL_BQ, 'header': HEADER, 'quickchg': QUICKCHG, 'strategy': STRATEGY}
        replacements = {name: str(safe(workspace, path)) for name, path in names.items()}
        replacements.update({'before_bq': str(safe(before_root, FULL_BQ)),
                             'before_quickchg': str(safe(before_root, QUICKCHG))})
        reports = []
        for job in tests['jobs']:
            require(isinstance(job.get('arguments'), list) and all(isinstance(a, str) for a in job['arguments']),
                    'Explicit production test arguments required')
            command = [sys.executable, str(safe(route, job['script']))] + [
                a.format(**dict(replacements, output=str(output / job['name']))) for a in job['arguments']]
            result = subprocess.run(command, capture_output=True, text=True)
            (output / (job['name'] + '.log')).write_text(result.stdout + result.stderr)
            require(result.returncode == 0, job['name'] + ' production C failed: ' + result.stdout + result.stderr)
            reports.append({'name': job['name'], 'script': job['script'],
                            'script_pin': pin(safe(route, job['script']).read_bytes()), 'returncode': result.returncode})
        record = {'schema': 1, 'status': 'PASS_R86_COMPOSED_PRODUCTION_SOURCES',
                  'actual_prepared_workspace': bool(args.workspace), 'tests': reports,
                  'sources': {row['path']: pin(safe(workspace, row['path']).read_bytes()) for row in contract['writes']},
                  'target_compile_tested': False, 'hardware_tested': False}
        (output / 'RESULT.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
        print(json.dumps({'status': record['status'], 'tests': [r['name'] for r in reports]}))


if __name__ == '__main__':
    main()
