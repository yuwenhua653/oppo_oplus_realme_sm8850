#!/usr/bin/env python3
"""Exercise exact R84 production sources; preflight and actual prepared source modes."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from apply_fastcharge import WRITES, apply, pin, require, safe, source_contract


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    route = Path(__file__).resolve().parent; repo = route.parent
    contract = source_contract(route)
    tests = json.loads((route / 'TEST-CONTRACT.json').read_text())
    jobs = tests['jobs']
    require(len(jobs) == 3 and {j['name'] for j in jobs} == {'adc', 'gauge', 'usb_psy'} and
            {j['source'] for j in jobs} == WRITES, 'Unexpected production test scope')
    output = args.output.resolve()
    require(not output.exists() and not output.is_symlink(), 'Fresh test output required')
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='r84-source-tests-') as temporary:
        if args.workspace:
            workspace = args.workspace.resolve()
            apply(workspace, route, verify=True)
        else:
            workspace = Path(temporary) / 'workspace'
            for row in contract['writes']:
                target = safe(workspace, row['path']); target.parent.mkdir(parents=True, exist_ok=True)
                data = safe(repo, row['preimage_source']).read_bytes()
                require(pin(data) == row['before'], 'Wrong offline source preimage')
                target.write_bytes(data)
            for row in contract['read_only_guards']:
                target = safe(workspace, row['path']); target.parent.mkdir(parents=True, exist_ok=True)
                data = safe(repo, row['source']).read_bytes()
                require(pin(data) == row['expected'], 'Wrong offline source guard')
                target.write_bytes(data)
            apply(workspace, route)
        after = {r['path']: r['after'] for r in contract['writes']}
        preimages = {r['path']: r for r in contract['writes']}
        reports = []
        for job in jobs:
            source = safe(workspace, job['source'])
            require(pin(source.read_bytes()) == after[job['source']], 'Test must execute exact frozen production postimage')
            script = safe(route, job['script'])
            command = [sys.executable, str(script), '--source', str(source), job['output_flag'], str(output / job['name'])]
            p = subprocess.run(command, text=True, capture_output=True)
            (output / (job['name'] + '.log')).write_text(p.stdout + p.stderr)
            require(p.returncode == 0, job['name'] + ' production tests failed: ' + p.stdout + p.stderr)
            reports.append({'name': job['name'], 'source': job['source'], **pin(source.read_bytes()),
                            'script': job['script'], 'returncode': p.returncode})
            if job['name'] == 'adc':
                require(job.get('negative_original') is True, 'ADC original runtime-assertion proof is required')
                row = preimages[job['source']]
                original = safe(repo, row['preimage_source'])
                require(pin(original.read_bytes()) == row['before'], 'Wrong original ADC test source')
                negative = [sys.executable, str(script), '--original', '--source', str(original),
                            job['output_flag'], str(output / 'adc-original')]
                proof = subprocess.run(negative, text=True, capture_output=True)
                (output / 'adc-original.log').write_text(proof.stdout + proof.stderr)
                require(proof.returncode == 0, 'Original ADC did not reproduce the specific expected runtime assertion: ' + proof.stdout + proof.stderr)
                reports[-1]['original_negative_proof'] = {'returncode': 0, **pin(original.read_bytes())}
        (output / 'RESULT.json').write_text(json.dumps({'schema': 1, 'status': 'PASS_R84_PRODUCTION_SOURCES',
            'actual_prepared_workspace': bool(args.workspace), 'tests': reports,
            'target_compile_tested': False, 'hardware_tested': False}, indent=2) + '\n')
        print(json.dumps({'status': 'PASS_R84_PRODUCTION_SOURCES', 'tests': [r['name'] for r in reports]}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
