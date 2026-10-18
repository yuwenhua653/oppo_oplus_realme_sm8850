#!/usr/bin/env python3
"""Compile only the three unchanged readonly modules and new standalone observer."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from thermal_inputs import check, parents, overlay_bytes, PARENT
parents(Path(__file__).resolve().parents[1])
from check_charge_inputs import load, require, safe, sha
from build_charge import write, verify_pair_metadata, verify_gauge_metadata
from apply_thermal import apply


def verify_applied(root,repo,inherited,c):
    _,_,parent,prior=parents(repo)
    expected={r['path']:r['sha256'] for r in inherited['workspace_files']}
    expected.update({r['destination']:r['after_sha256'] for r in prior['writes']+parent['writes']+c['writes']})
    for relative,digest in expected.items():
        require(sha(safe(root,relative).read_bytes())==digest,'Integrated source mismatch: '+relative)


def verify_observer_metadata(module):
    require(module['name']=='myron_buck_thermal','Observer module name differs')
    require(module['depends']==[] and not module['exports'],'Observer must be standalone and export no private symbols')
    require(module['info'].get('parmtype',[])==['enable_observer:bool'],'Exact compiled observer opt-in required')
    require(not module['info'].get('softdep'),'Observer must not request module autoload dependencies')
    forbidden=('mca_','pmic_glink_','platform_class_','power_supply_','thermal_','devm_thermal_',
               'regulator_','devm_regulator_','i2c_','devm_i2c_','vote','qcom_scm_')
    require(not any(n.startswith(forbidden) for n in module['imports']),'Observer acquired a forbidden control/provider interface')
    return {'status':'PASS_COMPILED_STANDALONE_OBSERVER_ONLY','module_dependencies':[],
            'private_exports':[],'boolean_module_parameters':['enable_observer:bool'],
            'runtime_load_approved':False,'hardware_control_implemented':False,
            'runtime_abi_compatible':'NOT_YET_VALIDATED'}


def verify_build_wiring(graph,observer,omitted_targets):
    labels={str(r['id']):r['label'] for r in graph.get('targets',[])}
    actions=graph.get('actions',[])
    makefiles=[a for a in actions if a.get('mnemonic')=='DdkMakefiles' and
               labels.get(str(a.get('targetId')))==observer['target']+'_makefiles']
    require(len(makefiles)==1,'Observer needs exactly one real DDK Makefile generator')
    args=makefiles[0].get('arguments',[])
    require('--produce-top-level-makefile' in args,'DDK must generate the observer Makefile')
    for option,value in [('--kernel-module-out','myron_buck_thermal.ko'),('--package','vendor/qcom/sm8850')]:
        require(args.count(option)==1 and args.index(option)+1<len(args) and args[args.index(option)+1]==value,
                'DDK generated Makefile module mapping changed')
    require(not any(a.get('mnemonic')=='KernelModule' and labels.get(str(a.get('targetId'))) in omitted_targets
                    for a in actions),'Unchanged MCA foundation target unexpectedly selected for compilation')
    return {'status':'PASS_AQUERY_GENERATED_MAKEFILE_WIRING','target':observer['target'],
            'generator_action_key':makefiles[0].get('actionKey'),'top_level_makefile_generated':True,
            'old_foundation_compiler_actions_present':False,'runtime_modulelist_changed':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'package', 'baseline', 'r18', 'repo-root'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    root, package, baseline, r18, repo = [getattr(args, n).resolve() for n in ('workspace', 'package', 'baseline', 'r18', 'repo_root')]
    reports = root / 'integration-reports'
    output = root / 'integration-artifacts/r77-targeted-thermal'
    contract_path = repo / 'r77-build-route/thermal-contract.json'
    status_path = reports / 'r77-status.json'
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
        shared = load('r77_shared_build_helpers', repo / 'r61-build-route/targeted_battery_build.py')
        old = load('r77_r18', r18 / 'boot_build.py')
        status['r18_bundle_lock_sha256'] = old.verify_bundle()
        helper = load('r77_driver', baseline / 'drivers/driver_check.py')
        runner_data, status['baseline_runner'] = helper.verify_bundle(baseline, package / 'build_platform.py')
        require(sha((package / 'sources.lock.json').read_bytes()) == contract['sources_lock_sha256'], 'Sources lock mismatch')
        bazel, options = helper.runner_build_configuration(runner_data, root, args.jobs, 10000)
        runner = load('r77_platform', package / 'build_platform.py')
        def logged(command, name):
            runner.logged(command, root, reports / ('r77-' + name + '.log'))
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
        write(reports / 'r77-overlay-apply.json', apply(root, repo, contract))
        write(reports / 'r77-overlay-check.json', apply(root, repo, contract, verify=True))
        verify_applied(root, repo, inherited, contract)
        runner.build_targets(root, 'soc')  # Emit kernel-release filegroup only; no aggregate build.
        selected = contract['modules']
        targets = [row['target'] for row in selected] + contract['core_targets']
        require(len(targets) == len(set(targets)), 'Duplicate build targets')
        plan = {'build': bazel + ['build'] + options + targets,
                'cquery': bazel + ['cquery'] + options + ['--output=files', 'deps(set(' + ' '.join(targets) + '))']}
        write(reports / 'r77-commands.json', plan)
        status.update(phase='analyze_four_targets', explicit_build_targets=targets)
        write(status_path, status)
        command = bazel + ['aquery'] + options + ['--output=jsonproto', '--include_artifacts=true',
                   '--include_commandline=true', 'deps(set(' + ' '.join(row['target'] for row in selected) + '))']
        result = subprocess.run(command, cwd=root, text=True, capture_output=True)
        (reports / 'r77-aquery.json').write_text(result.stdout)
        (reports / 'r77-aquery.log').write_text(result.stderr)
        require(result.returncode == 0, 'aquery failed before compilation')
        graph = json.loads(result.stdout)
        _, _, foundation, _ = parents(repo)
        omitted = [r['target'] for r in foundation['modules'] if r['module_name'] in contract['not_rebuilt_foundation_targets']]
        write(reports / 'r77-ddk-wiring.json', verify_build_wiring(graph, selected[-1], omitted))
        required_outputs = {row[key] for row in selected for key in ('output', 'symvers')}
        require(required_outputs <= shared.declared_outputs(graph), 'Predicted KO/symvers missing from action graph')
        for row in selected:
            write(reports / ('r77-action-' + row['module_name'] + '.json'),
                  shared.action_chain(graph, row['expected_sources'], row['output']))
        status['phase'] = 'compile_four_targets_and_core'
        write(status_path, status)
        logged(plan['build'], 'build')
        result = subprocess.run(plan['cquery'], cwd=root, text=True, capture_output=True)
        (reports / 'r77-cquery.txt').write_text(result.stdout)
        (reports / 'r77-cquery.log').write_text(result.stderr)
        require(result.returncode == 0, 'cquery failed after build')
        verify_applied(root, repo, inherited, contract)
        status['phase'] = 'collect_verified_outputs'
        write(status_path, status)
        status.update(shared.collect_outputs(root, output, contract, selected, result.stdout.splitlines(), r18))
        from elf_contract import parse_elf
        compiled = {r['module_name']: parse_elf((output / 'objects' / r['output']).read_bytes()) for r in selected}
        write(output / 'compiled-pair-review.json', verify_pair_metadata(
            compiled['myron_mca_readonly'], compiled['qti_pmic_glink']))
        write(output / 'compiled-gauge-review.json', verify_gauge_metadata(compiled['myron_bq_readonly']))
        write(output / 'compiled-observer-review.json', verify_observer_metadata(compiled['myron_buck_thermal']))
        for name, expected in contract['unchanged_readonly_KOs'].items():
            row = next(r for r in selected if r['module_name'] == name)
            data = (output / 'objects' / row['output']).read_bytes()
            require({'bytes': len(data), 'sha256': sha(data)} == expected, 'Existing readonly KO changed: ' + name)
        require(json.loads((output / 'module-inventory.json').read_text())['module_count'] == 4,
                'Collected KO scope changed')
        status.update(success=True, compiled=True, phase='compiled_source_bound_not_runtime_approved',
                      limitation='Old runtime Image remains authoritative. Check all imports, CRCs, namespaces, exports, CFI and retained QTI consumer compatibility before assembly.')
        write(status_path, status)
        shutil.copy2(contract_path, output / 'thermal-contract.json')
        shutil.copy2(repo / PARENT, output / 'parent-r76-contract.json')
        shutil.copy2(repo / 'r75-build-route/charge-contract.json', output / 'parent-r75-contract.json')
        (output / 'reports').mkdir()
        for report in sorted(reports.glob('r77-*')):
            if report.is_file():
                shutil.copy2(report, output / 'reports' / report.name)
        write(output / 'artifact-lock.json', {'schema': 1, 'compile_only': True, 'files': [
            {'file': str(p.relative_to(output)), 'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())}
            for p in sorted(output.rglob('*')) if p.is_file()]})
        # Written last. No verified output upload is eligible on a partial collection.
        write(output / 'candidate-complete.json', {'schema': 1, 'compile_only': True, 'flashable': False,
              'required_module_count': 4, 'runtime_abi_compatible': 'NOT_YET_VALIDATED',
              'artifact_lock_sha256': sha((output / 'artifact-lock.json').read_bytes()),
              'source_contract_sha256': status['source_contract_sha256']})
    except Exception as error:
        status.update(success=False, error=str(error))
        print('R77 STOP:', error, file=sys.stderr)
    finally:
        status['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        write(status_path, status)
    return 0 if status['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
