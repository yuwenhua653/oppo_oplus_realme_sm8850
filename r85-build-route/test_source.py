#!/usr/bin/env python3
"""Run author and independent suites on the exact composed production-C source."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from apply_bq import FULL_BQ, apply, pin, require, safe, source_contract

R84_BQ_SHA = 'd414cc63011673a36822de3a37b65580df96f44ad616f7cd9b3259655f807236'


def offline_guard_bytes(repo, guard):
    if 'source_parts' in guard:
        require(isinstance(guard['source_parts'], list) and guard['source_parts'], 'Explicit source guard recipe required')
        return b''.join(safe(repo, name).read_bytes() for name in guard['source_parts'])
    return safe(repo, guard['source']).read_bytes()


def reconstruct_r84_bq(repo, workspace):
    """Reconstruct the frozen R84 preimage from existing R61 + R83 inputs."""
    prior = json.loads((repo / 'r83-build-route/VALIDATION-SOURCE-CONTRACT.json').read_text())
    require(len(prior['writes']) == 1 and prior['writes'][0]['path'] == FULL_BQ and
            prior['writes'][0]['after']['sha256'] == R84_BQ_SHA,
            'Wrong inherited full-BQ preimage contract')
    row = prior['writes'][0]
    original = safe(repo, row['source']).read_bytes()
    require(pin(original) == row['before'], 'Wrong frozen R61 full-BQ input')
    target = safe(workspace, FULL_BQ)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(original)
    patch = safe(repo / 'r83-build-route', prior['patch']['path'])
    require(pin(patch.read_bytes()) == {key: prior['patch'][key] for key in ('bytes', 'sha256')} and
            prior['patch_working_directory'] == '.', 'Frozen R83 BQ boundaries patch changed')
    command = ['patch', '--batch', '--fuzz=0', '--forward', '-p1', '-i', str(patch)]
    subprocess.run(command + ['--dry-run'], cwd=workspace, check=True, capture_output=True)
    subprocess.run(command, cwd=workspace, check=True, capture_output=True)
    require(pin(target.read_bytes()) == row['after'], 'Reconstructed R84 BQ differs')
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    route = Path(__file__).resolve().parent
    repo = route.parent
    contract = source_contract(route)
    tests = json.loads((route / 'TEST-CONTRACT.json').read_text())
    jobs = tests['jobs']
    require(tests.get('schema') == 1 and tests.get('review_status') == 'FROZEN_REVIEWED_SOURCE' and
            len(jobs) == 3 and {job['name'] for job in jobs} == {'mac', 'probe', 'control'} and
            all(job['source'] == FULL_BQ for job in jobs), 'Unexpected production test scope')
    peer = tests.get('independent_merged')
    require(isinstance(peer, dict) and peer.get('name') == 'merged_peer' and peer.get('source') == FULL_BQ,
            'Independent composed-production suite required')
    jobs = jobs + [peer]
    output = args.output.resolve()
    require(not output.exists() and not output.is_symlink(), 'Fresh production test output required')
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='r85-production-tests-') as temporary:
        before_root = Path(temporary) / 'before'
        before_root.mkdir()
        before = reconstruct_r84_bq(repo, before_root)
        require(pin(before.read_bytes()) == contract['writes'][0]['before'], 'Wrong original negative-test source')
        if args.workspace:
            workspace = args.workspace.resolve()
            apply(workspace, route, verify=True)
        else:
            workspace = Path(temporary) / 'after'
            workspace.mkdir()
            reconstructed = reconstruct_r84_bq(repo, workspace)
            require(reconstructed == safe(workspace, FULL_BQ), 'Wrong reconstructed destination')
            for guard in contract['read_only_guards']:
                target = safe(workspace, guard['path'])
                target.parent.mkdir(parents=True, exist_ok=True)
                data = offline_guard_bytes(repo, guard)
                require(pin(data) == guard['expected'], 'Wrong offline source guard')
                target.write_bytes(data)
            apply(workspace, route)
        source = safe(workspace, FULL_BQ)
        require(pin(source.read_bytes()) == contract['writes'][0]['after'], 'Tests must execute the exact composed BQ source')
        reports = []
        substitutions = {'source': str(source), 'before': str(before),
                         'header': str(safe(workspace, contract['header_path']))}
        for job in jobs:
            script = safe(route, job['script'])
            job_output = output / job['name']
            replacements = dict(substitutions, output=str(job_output))
            require(isinstance(job.get('arguments'), list) and all(isinstance(arg, str) for arg in job['arguments']),
                    'Explicit production test arguments required')
            command = [sys.executable, str(script)] + [arg.format(**replacements) for arg in job['arguments']]
            result = subprocess.run(command, text=True, capture_output=True)
            (output / (job['name'] + '.log')).write_text(result.stdout + result.stderr)
            require(result.returncode == 0, job['name'] + ' production-C tests failed: ' + result.stdout + result.stderr)
            reports.append({'name': job['name'], 'source': FULL_BQ, **pin(source.read_bytes()),
                            'script': job['script'], 'script_pin': pin(script.read_bytes()),
                            'returncode': result.returncode, 'arguments': job['arguments']})
        (output / 'RESULT.json').write_text(json.dumps({'schema': 1, 'status': 'PASS_R85_COMPOSED_PRODUCTION_SOURCES',
            'actual_prepared_workspace': bool(args.workspace), 'tests': reports,
            'before': pin(before.read_bytes()), 'after': pin(source.read_bytes()),
            'target_compile_tested': False, 'hardware_tested': False}, indent=2, sort_keys=True) + '\n')
        print(json.dumps({'status': 'PASS_R85_COMPOSED_PRODUCTION_SOURCES', 'tests': [job['name'] for job in jobs]}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
