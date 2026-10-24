#!/usr/bin/env python3
"""Run the provider suite against the exact patched C that the build will compile."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from contract import PROVIDER, apply, check_overlay, pin, require, source_contract
from build_pd_provider import write


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    route = Path(__file__).resolve().parent
    repo, root, out = route.parent, args.workspace.resolve(), args.output.resolve()
    check_overlay(repo)
    verification = apply(root, repo, verify=True)
    actual = root / PROVIDER
    require(actual.read_bytes() == (route / 'payload/qcom_adsp_pd_protocol.c').read_bytes(),
            'Actual production C differs from reviewed provider payload')
    require(not out.exists() and not out.is_symlink(), 'Fresh R92 host report path required')
    out.mkdir(parents=True)
    command = [sys.executable, '-B', str(route / 'tests/provider/run_tests.py'),
               '--source', str(actual), '--out', str(out / 'provider')]
    result = subprocess.run(command, capture_output=True, text=True, timeout=240)
    (out / 'provider-tests.log').write_text(result.stdout + result.stderr)
    require(result.returncode == 0, 'Actual provider source host tests failed: ' + result.stdout + result.stderr)
    record = {'schema': 1, 'status': 'PASS_R92_PRODUCTION_PROVIDER_SOURCE_TESTS',
              'source': {'path': PROVIDER, **pin(actual.read_bytes())},
              'test_runner': {'path': 'tests/provider/run_tests.py', **pin((route / 'tests/provider/run_tests.py').read_bytes())},
              'R90_source_guards_verified': verification['R90_sources_unchanged'],
              'target_compile_tested': False, 'hardware_tested': False,
              'limit': 'Actual prepared provider C host tests; complete AArch64 48-module build follows in CI.'}
    write(out / 'RESULT.json', record)
    print(json.dumps(record))


if __name__ == '__main__':
    main()
