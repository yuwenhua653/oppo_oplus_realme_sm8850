#!/usr/bin/env python3
"""Execute exact prepared R87 charging sources and the true FG type enum."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from apply_safety import (CP, FG_HEADER, FULL_BQ, HEADER, PREFIX, QUICKCHG, STRATEGY,
                          USB, apply, pin, require, safe, source_contract)
from build_safety import frozen_r86


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def reconstruct_r86(repo, workspace):
    r86 = frozen_r86(repo)
    r86.check(repo)
    previous = r86.source_contract(repo / 'r86-build-route')
    old = r86.load('r87_parent_test_source', repo / 'r86-build-route/test_source.py')
    old.reconstruct_inputs(repo, workspace, previous)
    r86.apply(workspace, repo / 'r86-build-route')
    for path in (CP,):
        write(safe(workspace, path), safe(repo, 'r61-build-route/payload/' + path.removeprefix(PREFIX)).read_bytes())
    r84 = json.loads((repo / 'r84-build-route/SOURCE-CONTRACT.json').read_text())
    usb = next(row for row in r84['writes'] if row['path'] == USB)
    patch = next(row for row in r84['patches'] if row['file'] == 'usb-psy-errors.patch')
    write(safe(workspace, USB), safe(repo, usb['preimage_source']).read_bytes())
    require(pin(safe(workspace, USB).read_bytes()) == usb['before'], 'Wrong R84 USB preimage')
    patch_path = repo / 'r84-build-route' / patch['file']
    require(pin(patch_path.read_bytes()) == {key: patch[key] for key in ('bytes', 'sha256')} and
            patch['working_directory'] == '.', 'Wrong frozen USB patch')
    subprocess.run(['patch', '--batch', '--fuzz=0', '--forward', '-p1', '-i', str(patch_path)],
                   cwd=workspace, check=True, capture_output=True)
    require(pin(safe(workspace, USB).read_bytes()) == usb['after'], 'Wrong inherited USB postimage')
    return r86, old


def guard_bytes(repo, workspace, guard, old_test):
    if guard.get('inherited_r86_postimage'):
        return safe(workspace, guard['path']).read_bytes()
    return old_test.offline_guard_bytes(repo, guard)


def reconstruct_inputs(repo, workspace, contract):
    r86, _ = reconstruct_r86(repo, workspace)
    r85 = r86.frozen_r85(repo)
    old_test = r85.load('r87_offline_guard_recipe', repo / 'r85-build-route/test_source.py')
    for guard in contract['read_only_guards']:
        data = guard_bytes(repo, workspace, guard, old_test)
        require(pin(data) == guard['expected'], 'Wrong offline R87 guard: ' + guard['path'])
        write(safe(workspace, guard['path']), data)
    for row in contract['writes']:
        require(pin(safe(workspace, row['path']).read_bytes()) == row['before'], 'Wrong reconstructed R86 preimage')


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
            {j['name'] for j in tests.get('jobs', [])} == {'cp', 'quickchg', 'fanout'} and len(tests['jobs']) == 3,
            'Exact CP, quickchg and true-enum fanout production suites required')
    output = args.output.resolve()
    require(not output.exists() and not output.is_symlink(), 'Fresh production test output required')
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='r87-production-tests-') as temporary:
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
        names = {'cp': CP, 'usb': USB, 'bq': FULL_BQ, 'header': HEADER, 'quickchg': QUICKCHG,
                 'strategy': STRATEGY, 'strategy_header': FG_HEADER}
        replacements = {name: str(safe(workspace, path)) for name, path in names.items()}
        replacements.update({'before_cp': str(safe(before_root, CP)), 'before_usb': str(safe(before_root, USB)),
                             'before_quickchg': str(safe(before_root, QUICKCHG))})
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
        record = {'schema': 1, 'status': 'PASS_R87_COMPOSED_PRODUCTION_SOURCES',
                  'actual_prepared_workspace': bool(args.workspace), 'tests': reports,
                  'sources': {row['path']: pin(safe(workspace, row['path']).read_bytes()) for row in contract['writes']},
                  'strategy_enum_header': pin(safe(workspace, FG_HEADER).read_bytes()),
                  'target_compile_tested': False, 'hardware_tested': False}
        (output / 'RESULT.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
        print(json.dumps({'status': record['status'], 'tests': [r['name'] for r in reports]}))


if __name__ == '__main__':
    main()
