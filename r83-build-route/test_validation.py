#!/usr/bin/env python3
"""Run actual inactive BQ production functions against controlled I2C results."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from validation_only import prepare, BQ, SOURCES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    route = Path(__file__).resolve().parent
    repo = route.parent
    source = json.loads((route / 'VALIDATION-SOURCE-CONTRACT.json').read_text())
    with tempfile.TemporaryDirectory(prefix='r83-inactive-tests-') as temporary:
        scratch = Path(temporary)
        if args.workspace:
            workspace = args.workspace.resolve()
            prepare(workspace, route, verify=True)
        else:
            workspace = scratch / 'workspace'
            for row in source['writes'] + source['read_only_guards']:
                target = workspace / row['path']
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(repo / row['source'], target)
            prepare(workspace, route)
            prepare(workspace, route, verify=True)
        output = args.output.resolve() if args.output else scratch / 'test-output'
        result = subprocess.run([sys.executable, str(route / 'tests/bq/test_bq_boundaries.py'),
            '--source', str(workspace / (SOURCES + BQ + '.c')),
            '--header', str(workspace / (SOURCES + str(Path(BQ).parent) + '/inc/bq27z561.h')),
            '--output', str(output)], check=False)
        return result.returncode


if __name__ == '__main__':
    sys.exit(main())
