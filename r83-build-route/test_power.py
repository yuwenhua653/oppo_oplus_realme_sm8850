#!/usr/bin/env python3
"""Execute the complete patched production C source under host kernel stubs."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from apply_power import apply, SOURCE, pin


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    route = Path(__file__).resolve().parent
    repo = route.parent
    contract = json.loads((route / 'SOURCE-CONTRACT.json').read_text())
    with tempfile.TemporaryDirectory(prefix='r83-source-tests-') as temporary:
        scratch = Path(temporary)
        if args.workspace:
            workspace = args.workspace.resolve()
            apply(workspace, route, verify=True)
        else:
            workspace = scratch / 'workspace'
            for row in contract['writes'] + contract['read_only_guards']:
                target = workspace / row['path']
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(repo / row['source'], target)
            apply(workspace, route)
            apply(workspace, route, verify=True)
        source = workspace / SOURCE
        if pin(source.read_bytes()) != contract['writes'][0]['after']:
            raise ValueError('Tests must execute the exact frozen production postimage')
        output = args.output.resolve() if args.output else scratch / 'test-output'
        result = subprocess.run([sys.executable, str(route / 'tests/client/run_tests.py'),
             '--source', str(source), '--header', str(workspace / 'vendor/qcom/sm8850/include/linux/soc/qcom/qti_pmic_glink.h'),
             '--output', str(output)], check=False)
        return result.returncode


if __name__ == '__main__':
    sys.exit(main())
