#!/usr/bin/env python3
"""Run the frozen whole-source host tests before source sync and kernel build."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from check_charge_inputs import check, require, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--reports', required=True, type=Path)
    args = parser.parse_args()
    root, reports = args.root.resolve(), args.reports.resolve()
    contract = json.loads((root / 'r74-build-route/charge-contract.json').read_text())
    check(root, contract)
    reports.mkdir(parents=True, exist_ok=True)
    for row in contract['host_tests']:
        output = reports / ('r74-host-' + row['name'])
        require(not output.exists(), 'Use a fresh host-test output directory')
        cmd = [sys.executable, str(root / row['script']), '--source', str(root / row['source']), '--output', str(output)]
        if row.get('header'):
            cmd.extend(['--header', str(root / row['header'])])
        process = subprocess.run(cmd, cwd=root, text=True, capture_output=True)
        (reports / ('r74-host-' + row['name'] + '.log')).write_text(process.stdout + process.stderr)
        require(process.returncode == 0, 'Production source host test failed: ' + row['name'])
        result_path = output / row['result_file']
        require(result_path.is_file(), 'Missing host test result: ' + row['name'])
        result = json.loads(result_path.read_text())
        require(result.get('status') == 'PASS', 'Host test result not PASS')
        require(result.get('source_sha256') == sha((root / row['source']).read_bytes()),
                'Host test did not report testing the frozen production source')
        if row.get('header'):
            require(result.get('header_sha256' if row['name'] == 'transport' else 'public_header_sha256') == sha((root / row['header']).read_bytes()),
                    'Host test did not report testing the compiled public header')
    print('R74 frozen production source host tests passed; device/kernel behavior is not claimed.')


if __name__ == '__main__':
    main()
