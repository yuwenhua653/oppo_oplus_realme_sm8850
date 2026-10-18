#!/usr/bin/env python3
"""Compile only the three R75 targets with the locked R13/R60/R61 preparation."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from check_charge_inputs import check, load, require, safe, sha
from apply_charge import apply


def write(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + '\n')


def verify_applied(root, inherited, contract):
    expected = {row['path']: row['sha256'] for row in inherited['workspace_files']}
    expected.update({row['destination']: row['after_sha256'] for row in contract['writes']})
    for relative, expected_sha in expected.items():
        require(sha(safe(root, relative).read_bytes()) == expected_sha, 'Integrated source mismatch: ' + relative)



def verify_pair_metadata(client, transport):
    symbol = 'pmic_glink_unregister_client_sync'
    require(client['name'] == 'myron_mca_readonly' and transport['name'] == 'qti_pmic_glink', 'Pair identities differ')
    require(symbol in client['imports'] and symbol in client['versions'], 'Client lacks mandatory new-backend import')
    require('pmic_glink_unregister_client' not in client['imports'], 'Old unregister fallback is forbidden')
    require(symbol in transport['exports'] and symbol in transport['export_crcs'], 'New QTI backend export missing')
    require(client['versions'][symbol] == transport['export_crcs'][symbol], 'Paired unregister CRC mismatch')
    require(client['depends'] == ['qti_pmic_glink'], 'Unexpected read-only client module dependency')
    parameters = client['info'].get('parmtype', [])
    require(len(parameters) == 3 and set(parameters) == {
                'enable_readonly:bool', 'enable_power_supply:bool', 'enable_extra_diagnostics:bool'},
            'Compiled client boolean parameter allowlist differs')
    return {'status': 'PASS_COMPILED_PAIR_ONLY', 'symbol': symbol, 'import_crc': hex(client['versions'][symbol]),
            'export_crc': hex(transport['export_crcs'][symbol]), 'old_unregister_imported': False,
            'boolean_module_parameters': sorted(client['info']['parmtype']),
            'runtime_abi_compatible': 'NOT_YET_VALIDATED'}


def verify_gauge_metadata(gauge):
    require(gauge['name'] == 'myron_bq_readonly', 'Independent gauge identity differs')
    require(gauge['depends'] == [], 'Gauge acquired an unexpected module dependency')
    require(not any(name.startswith(('pmic_glink_', 'mca_')) for name in gauge['imports']),
            'Gauge must use only the core power_supply interface for charger state')
    return {'status': 'PASS_COMPILED_GAUGE_ONLY', 'module': gauge['name'],
            'module_dependencies': [], 'runtime_abi_compatible': 'NOT_YET_VALIDATED'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'package', 'baseline', 'r18', 'repo-root'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    root, package, baseline, r18, repo = [getattr(args, n).resolve() for n in ('workspace', 'package', 'baseline', 'r18', 'repo_root')]
    reports = root / 'integration-reports'
    output = root / 'integration-artifacts/r75-targeted-charge'
    contract_path = repo / 'r75-build-route/charge-contract.json'
    status_path = reports / 'r75-status.json'
    status = {'schema': 1, 'success': False, 'compile_only': True, 'flashable': False,
              'hardware_tested': False, 'runtime_abi_compatible': 'NOT_YET_VALIDATED',
              'github': {key: os.environ.get(key, '') for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')},
              'phase': 'preflight', 'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    write(status_path, status)
    try:
        require(1 <= args.jobs <= 4, 'Invalid job count')
        require(not output.is_symlink(), 'Redirected output')
        require(not output.exists(), 'Refusing existing output; use a fresh CI workspace')
        contract = json.loads(contract_path.read_text())
        check(repo, contract)
        status['source_contract_sha256'] = sha(contract_path.read_bytes())
        inherited = json.loads((repo / contract['base_contract']).read_text())
        sys.path.insert(0, str(repo / 'r61-build-route'))
        shared = load('r75_shared_build_helpers', repo / 'r61-build-route/targeted_battery_build.py')
        old = load('r75_r18', r18 / 'boot_build.py')
        status['r18_bundle_lock_sha256'] = old.verify_bundle()
        helper = load('r75_driver', baseline / 'drivers/driver_check.py')
        runner_data, status['baseline_runner'] = helper.verify_bundle(baseline, package / 'build_platform.py')
        require(sha((package / 'sources.lock.json').read_bytes()) == contract['sources_lock_sha256'], 'Sources lock mismatch')
        bazel, options = helper.runner_build_configuration(runner_data, root, args.jobs, 10000)
        runner = load('r75_platform', package / 'build_platform.py')
        def logged(command, name):
            runner.logged(command, root, reports / ('r75-' + name + '.log'))
        status['phase'] = 'prepare_exact_sources'
        write(status_path, status)
        logged([sys.executable, str(package / 'prepare_workspace.py'), '--workspace', str(root)], 'prepare')
        logged([sys.executable, str(baseline / 'run_r12.py'), 'apply', '--workspace', str(root), '--stage', 'soc'], 'r13-apply')
        helper.verify_applied_writes(baseline, root)
        hardware = json.loads((repo / inherited['prerequisite_contract']).read_text())
        for name, source_contract in [('r60', hardware), ('r61', inherited)]:
            command = [sys.executable, str(repo / source_contract['integration']['script']), '--workspace', str(root)]
            logged(command, name + '-apply')
            logged(command + ['--check'], name + '-check')
            shared.locked_workspace(root, source_contract['workspace_files'])
        write(reports / 'r75-overlay-apply.json', apply(root, repo, contract))
        write(reports / 'r75-overlay-check.json', apply(root, repo, contract, verify=True))
        verify_applied(root, inherited, contract)
        runner.build_targets(root, 'soc')  # Emit kernel-release filegroup only; no aggregate build.
        selected = contract['modules']
        targets = [row['target'] for row in selected] + contract['core_targets']
        require(len(targets) == len(set(targets)), 'Duplicate build targets')
        plan = {'build': bazel + ['build'] + options + targets,
                'cquery': bazel + ['cquery'] + options + ['--output=files', 'deps(set(' + ' '.join(targets) + '))']}
        write(reports / 'r75-commands.json', plan)
        status.update(phase='analyze_three_targets', explicit_build_targets=targets)
        write(status_path, status)
        command = bazel + ['aquery'] + options + ['--output=jsonproto', '--include_artifacts=true',
                   '--include_commandline=true', 'deps(set(' + ' '.join(row['target'] for row in selected) + '))']
        result = subprocess.run(command, cwd=root, text=True, capture_output=True)
        (reports / 'r75-aquery.json').write_text(result.stdout)
        (reports / 'r75-aquery.log').write_text(result.stderr)
        require(result.returncode == 0, 'aquery failed before compilation')
        graph = json.loads(result.stdout)
        required_outputs = {row[key] for row in selected for key in ('output', 'symvers')}
        require(required_outputs <= shared.declared_outputs(graph), 'Predicted KO/symvers missing from action graph')
        for row in selected:
            write(reports / ('r75-action-' + row['module_name'] + '.json'),
                  shared.action_chain(graph, row['expected_sources'], row['output']))
        status['phase'] = 'compile_three_targets_and_core'
        write(status_path, status)
        logged(plan['build'], 'build')
        result = subprocess.run(plan['cquery'], cwd=root, text=True, capture_output=True)
        (reports / 'r75-cquery.txt').write_text(result.stdout)
        (reports / 'r75-cquery.log').write_text(result.stderr)
        require(result.returncode == 0, 'cquery failed after build')
        verify_applied(root, inherited, contract)
        status['phase'] = 'collect_verified_outputs'
        write(status_path, status)
        status.update(shared.collect_outputs(root, output, contract, selected, result.stdout.splitlines(), r18))
        from elf_contract import parse_elf
        compiled = {r['module_name']: parse_elf((output / 'objects' / r['output']).read_bytes()) for r in selected}
        write(output / 'compiled-pair-review.json', verify_pair_metadata(
            compiled['myron_mca_readonly'], compiled['qti_pmic_glink']))
        write(output / 'compiled-gauge-review.json', verify_gauge_metadata(compiled['myron_bq_readonly']))
        require(json.loads((output / 'module-inventory.json').read_text())['module_count'] == 3,
                'Collected KO scope changed')
        status.update(success=True, compiled=True, phase='compiled_source_bound_not_runtime_approved',
                      limitation='Old runtime Image remains authoritative. Check all imports, CRCs, namespaces, exports, CFI and retained QTI consumer compatibility before assembly.')
        write(status_path, status)
        shutil.copy2(contract_path, output / 'charge-contract.json')
        (output / 'reports').mkdir()
        for report in sorted(reports.glob('r75-*')):
            if report.is_file():
                shutil.copy2(report, output / 'reports' / report.name)
        write(output / 'artifact-lock.json', {'schema': 1, 'compile_only': True, 'files': [
            {'file': str(p.relative_to(output)), 'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())}
            for p in sorted(output.rglob('*')) if p.is_file()]})
        # Written last. No verified output upload is eligible on a partial collection.
        write(output / 'candidate-complete.json', {'schema': 1, 'compile_only': True, 'flashable': False,
              'required_module_count': 3, 'runtime_abi_compatible': 'NOT_YET_VALIDATED',
              'artifact_lock_sha256': sha((output / 'artifact-lock.json').read_bytes()),
              'source_contract_sha256': status['source_contract_sha256']})
    except Exception as error:
        status.update(success=False, error=str(error))
        print('R75 STOP:', error, file=sys.stderr)
    finally:
        status['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        write(status_path, status)
    return 0 if status['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
