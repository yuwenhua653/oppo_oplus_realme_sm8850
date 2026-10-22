#!/usr/bin/env python3
"""Compile R86 state/error fixes after exact R85 preparation; outputs stay inactive."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from apply_control import (BASE_COMMIT, C_WRITES, FULL_BQ, HEADER, PARENT, PARENT_SHA,
                           PARENT_SOURCE_SHA, WRITES, apply, pin, require, safe, source_contract)


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frozen_r85(repo):
    require(pin((repo / PARENT).read_bytes())['sha256'] == PARENT_SHA, 'Frozen R85 build contract changed')
    require(pin((repo / 'r85-build-route/SOURCE-CONTRACT.json').read_bytes())['sha256'] == PARENT_SOURCE_SHA,
            'Frozen R85 source contract changed')
    sys.path.insert(0, str(repo / 'r85-build-route'))
    return load('r86_frozen_r85', repo / 'r85-build-route/build_bq.py')


def parent_postimages(repo, pc, parent_inputs, r84, r85):
    expected = r85.parent_postimages(repo, pc, parent_inputs, r84)
    previous = r85.source_contract(repo / 'r85-build-route')
    for row in previous['read_only_guards']:
        digest = row['expected']['sha256']
        require(row['path'] not in expected or expected[row['path']] == digest, 'R85 guard disagrees with ancestry')
        expected[row['path']] = digest
    for row in previous['writes']:
        require(expected.get(row['path']) == row['before']['sha256'], 'R85 postimage ancestry mismatch')
        expected[row['path']] = row['after']['sha256']
    return expected


def check(repo):
    route = repo / 'r86-build-route'
    r85 = frozen_r85(repo)
    previous, _, pc, parent_inputs, r83, r84 = r85.check(repo)
    contract = json.loads((route / 'build-contract.json').read_text())
    require(contract.get('schema') == 1 and contract.get('review_status') == 'FROZEN_REVIEWED_SOURCE' and
            contract.get('compile_only') is True and contract.get('flashable') is False,
            'Frozen R86 compile-only contract required')
    require(contract.get('base_commit') == BASE_COMMIT and contract.get('parent_contract') == PARENT and
            contract.get('parent_contract_sha256') == PARENT_SHA, 'Wrong R86 parent')
    for key in ('baseline_image_sha256', 'baseline_kernel_release', 'sources_lock_sha256', 'git_heads',
                'core_targets', 'validation_scope', 'validation_scope_sha256', 'validation_only_modules'):
        require(contract.get(key) == previous[key], 'Inherited source/core preparation changed: ' + key)
    rows = contract['locked_files']
    names = [row['path'] for row in rows]
    actual = {str(path.relative_to(repo)) for path in route.rglob('*') if path.is_file() and
              '__pycache__' not in path.parts and path.name != 'build-contract.json'}
    require(len(names) == len(set(names)) and set(names) == actual, 'R86 locked inventory changed')
    for row in rows:
        path = safe(repo, row['path'])
        require(path.resolve().is_relative_to(route.resolve()) and
                pin(path.read_bytes()) == {key: row[key] for key in ('bytes', 'sha256')},
                'R86 locked input changed: ' + row['path'])
    require(contract.get('modules') == [] and contract.get('runtime_candidate_module_names') == [] and
            contract.get('full_charging_control_enabled') is False and contract.get('activation_allowed') is False,
            'R86 full-MCA outputs must stay inactive')
    source = source_contract(route)
    expected = parent_postimages(repo, pc, parent_inputs, r84, r85)
    for row in source['read_only_guards']:
        require(row['path'] not in expected or expected[row['path']] == row['expected']['sha256'],
                'R86 source guard disagrees with frozen parent: ' + row['path'])
    for row in source['writes']:
        require(expected.get(row['path']) == row['before']['sha256'],
                'R86 overlay does not extend exact prepared R85 source: ' + row['path'])
    require(C_WRITES <= {name for row in contract['validation_only_modules'] for name in row['expected_sources']},
            'Changed C source does not feed a selected build action')
    require(contract.get('source_contract') == pin((route / 'SOURCE-CONTRACT.json').read_bytes()),
            'Build contract does not bind exact source contract')
    return contract, previous, pc, parent_inputs, r83, r84, r85


def verify_postimages(root, repo, pc, parent_inputs, r84, route):
    r85 = frozen_r85(repo)
    expected = parent_postimages(repo, pc, parent_inputs, r84, r85)
    source = source_contract(route)
    for row in source['read_only_guards']:
        digest = row['expected']['sha256']
        require(row['path'] not in expected or expected[row['path']] == digest, 'R86 source guard ancestry mismatch')
        expected[row['path']] = digest
    for row in source['writes']:
        require(expected.get(row['path']) == row['before']['sha256'], 'R86 source ancestor mismatch')
        expected[row['path']] = row['after']['sha256']
    for relative, digest in expected.items():
        require(pin(safe(root, relative).read_bytes())['sha256'] == digest, 'Integrated source changed: ' + relative)
    return {'schema': 1, 'status': 'PASS_ALL_INHERITED_AND_R86_POSTIMAGES',
            'checked_destinations': len(expected), 'exact_overlays': sorted(WRITES),
            'R84_ADC_gauge_USB_and_R83_MCA_sources_unchanged': True}


def verify_effective_bq_config(root, graph, modules):
    return frozen_r85(Path(__file__).resolve().parent.parent).verify_effective_bq_config(root, graph, modules)


def finalize(output, route, reports, status, config):
    policy = {'role': 'validation_only', 'compile_only': True, 'flashable': False,
              'activation_allowed': False, 'runtime_candidate_module_names': [],
              'full_charging_control_enabled': False, 'runtime_abi_compatible': 'NOT_YET_VALIDATED'}
    for name in ('artifact-manifest.json', 'module-inventory.json', 'module-identity.json'):
        path = output / name
        record = json.loads(path.read_text())
        record.update(policy)
        write(path, record)
    require(json.loads((output / 'module-inventory.json').read_text())['module_count'] == 47,
            'Final inventory must contain all47 inactive modules')
    shutil.copy2(route / 'build-contract.json', output / 'build-contract.json')
    shutil.copytree(route, output / 'source/r86-build-route', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(route.parent / 'r85-build-route', output / 'source/r85-build-route',
                    ignore=shutil.ignore_patterns('__pycache__'))
    compiled = []
    for row in source_contract(route)['writes']:
        source = safe(Path(config['workspace_root']), row['path'])
        require(pin(source.read_bytes()) == row['after'], 'Actual compiled source postimage changed: ' + row['path'])
        destination = output / 'compiled-source' / row['path']
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        compiled.append({'file': str(destination.relative_to(output)), **row['after']})
    destination = output / 'reports'
    destination.mkdir()
    for path in reports.rglob('*'):
        if path.is_file() and (path.name.startswith('r86-') or any(p.startswith('r86-') for p in path.parts)) and path.suffix in ('.json', '.log', '.txt'):
            target = destination / path.relative_to(reports)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    config_source = Path(config['workspace_root']) / config['config_path']
    require(pin(config_source.read_bytes()) == {key: config[key] for key in ('bytes', 'sha256')},
            'External module config changed during finalization')
    config_destination = output / 'module-config/canoe_perf.config'
    config_destination.parent.mkdir()
    shutil.copy2(config_source, config_destination)
    write(output / 'artifact-lock.json', {'schema': 1, **policy, 'files': [
        {'file': str(path.relative_to(output)), **pin(path.read_bytes())}
        for path in sorted(output.rglob('*')) if path.is_file()]})
    write(output / 'validation-complete.json', {'schema': 1, **policy, 'required_module_count': 47,
        'full_validation_success': True, 'build_contract_sha256': status['build_contract_sha256'],
        'source_contract_sha256': status['source_contract_sha256'], 'compiled_sources': compiled,
        'artifact_lock_sha256': pin((output / 'artifact-lock.json').read_bytes())['sha256']})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', required=True, type=Path)
    parser.add_argument('--check-inputs', action='store_true')
    for name in ('workspace', 'package', 'baseline', 'r18'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--ram-mb', type=int, default=10000)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    if args.check_inputs:
        contract, _, _, _, _, _, _ = check(repo)
        print(json.dumps({'status': 'PASS_R86_FROZEN_INPUTS', 'runtime_candidates': [],
                          'validation_only_count': 47, 'locked_inputs': len(contract['locked_files'])}))
        return 0
    require(all(getattr(args, name) is not None for name in ('workspace', 'package', 'baseline', 'r18')),
            'Four build paths required')
    root, package, baseline, r18 = [getattr(args, name).resolve() for name in ('workspace', 'package', 'baseline', 'r18')]
    route = repo / 'r86-build-route'
    reports = root / 'integration-reports'
    output = root / 'integration-artifacts/r86-mca-validation-only'
    status_path = reports / 'r86-status.json'
    status = {'schema': 1, 'success': False, 'validation_compiled': False, 'compile_only': True,
              'flashable': False, 'hardware_tested': False, 'activation_allowed': False,
              'full_charging_control_enabled': False, 'runtime_candidate_module_names': [],
              'github': {key: os.environ.get(key, '') for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')},
              'phase': 'preflight', 'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    write(status_path, status)
    final_config = None
    try:
        require(1 <= args.jobs <= 4 and args.ram_mb >= 2048, 'Invalid resource budget')
        require(not output.exists() and not output.is_symlink(), 'Fresh artifact path required')
        contract, _, pc, parent_inputs, r83, r84, r85 = check(repo)
        status['build_contract_sha256'] = pin((route / 'build-contract.json').read_bytes())['sha256']
        status['source_contract_sha256'] = pin((route / 'SOURCE-CONTRACT.json').read_bytes())['sha256']
        parent, multimedia = parent_inputs.parent(repo)
        thermal, thermal_contract = parent.parent(repo)
        inherited = json.loads((repo / thermal_contract['base_contract']).read_text())
        sys.path.insert(0, str(repo / 'r61-build-route'))
        shared = load('r86_shared', repo / 'r61-build-route/targeted_battery_build.py')
        resolver = load('r86_resolver', repo / 'r78-build-route/resolve_outputs.py')
        old = load('r86_r18', r18 / 'boot_build.py')
        status['r18_bundle_lock_sha256'] = old.verify_bundle()
        helper = load('r86_driver', baseline / 'drivers/driver_check.py')
        runner_data, status['baseline_runner'] = helper.verify_bundle(baseline, package / 'build_platform.py')
        require(pin((package / 'sources.lock.json').read_bytes())['sha256'] == contract['sources_lock_sha256'],
                'Source lock changed')
        bazel, options = helper.runner_build_configuration(runner_data, root, args.jobs, args.ram_mb)
        options = list(options) + ['--nokeep_going']
        runner = load('r86_platform', package / 'build_platform.py')
        def logged(command, name):
            runner.logged(command, root, reports / ('r86-' + name + '.log'))
        status['phase'] = 'prepare_frozen_R84_sources'
        write(status_path, status)
        logged([sys.executable, str(package / 'prepare_workspace.py'), '--workspace', str(root)], 'prepare')
        logged([sys.executable, str(baseline / 'run_r12.py'), 'apply', '--workspace', str(root), '--stage', 'soc'], 'r13-apply')
        helper.verify_applied_writes(baseline, root)
        hardware = json.loads((repo / inherited['prerequisite_contract']).read_text())
        for name, source in [('r60', hardware), ('r61', inherited)]:
            command = [sys.executable, str(repo / source['integration']['script']), '--workspace', str(root)]
            logged(command, name + '-apply')
            logged(command + ['--check'], name + '-check')
            shared.locked_workspace(root, source['workspace_files'])
        from apply_thermal import apply as apply_thermal
        from apply_multimedia import apply as apply_multimedia
        from apply_repairs import apply as apply_repairs, verify_applied
        for name, operation, source in [('thermal', apply_thermal, thermal_contract),
                                        ('multimedia', apply_multimedia, multimedia), ('repairs', apply_repairs, pc)]:
            write(reports / ('r86-parent-' + name + '-apply.json'), operation(root, repo, source))
            write(reports / ('r86-parent-' + name + '-check.json'), operation(root, repo, source, verify=True))
        write(reports / 'r86-parent-r79-postimages.json', verify_applied(root, repo, pc))
        power = load('r86_r83_power', repo / 'r83-build-route/apply_power.py')
        write(reports / 'r86-parent-r83-power.json', power.apply(root, repo / 'r83-build-route'))
        validation = load('r86_r83_validation', repo / 'r83-build-route/validation_only.py')
        write(reports / 'r86-parent-r83-validation.json', validation.prepare(root, repo / 'r83-build-route'))
        write(reports / 'r86-parent-r83-postimages.json',
              r83.verify_r83_postimages(root, repo, pc, parent_inputs, repo / 'r83-build-route'))
        write(reports / 'r86-parent-r84-source-apply.json', r84.apply(root, repo / 'r84-build-route'))
        write(reports / 'r86-parent-r84-source-check.json', r84.apply(root, repo / 'r84-build-route', verify=True))
        write(reports / 'r86-parent-r84-postimages.json',
              r84.verify_postimages(root, repo, pc, parent_inputs, repo / 'r84-build-route'))
        write(reports / 'r86-parent-r85-source-apply.json', r85.apply(root, repo / 'r85-build-route'))
        write(reports / 'r86-parent-r85-source-check.json', r85.apply(root, repo / 'r85-build-route', verify=True))
        write(reports / 'r86-parent-r85-postimages.json', r85.verify_postimages(root, repo, pc, parent_inputs, r84, repo / 'r85-build-route'))
        logged([sys.executable, str(repo / 'r85-build-route/test_source.py'), '--workspace', str(root), '--output', str(reports / 'r86-parent-r85-host')], 'parent-r85-production-source-tests')
        write(reports / 'r86-source-apply.json', apply(root, route))
        write(reports / 'r86-source-check.json', apply(root, route, verify=True))
        logged([sys.executable, str(route / 'test_source.py'), '--workspace', str(root),
                '--output', str(reports / 'r86-host')], 'production-source-tests')
        write(reports / 'r86-all-prebuild-postimages.json',
              verify_postimages(root, repo, pc, parent_inputs, r84, route))
        # This frozen helper emits the kernel.release filegroup only; its
        # returned aggregate labels are ignored. Bazel builds the47 explicit
        # MCA targets plus the retained core targets below.
        runner.build_targets(root, 'soc')
        module_targets = [row['target'] for row in contract['validation_only_modules']]
        build_targets = module_targets + contract['core_targets']
        status['phase'] = 'analyze_47_inactive_targets'
        write(status_path, status)
        analysis = bazel + ['aquery'] + options + ['--output=jsonproto', '--include_artifacts=true',
                   '--include_commandline=true', 'deps(set(' + ' '.join(module_targets) + '))']
        result = subprocess.run(analysis, cwd=root, text=True, capture_output=True)
        (reports / 'r86-aquery.json').write_text(result.stdout)
        (reports / 'r86-aquery.log').write_text(result.stderr)
        require(result.returncode == 0, 'Actual target aquery failed before compile')
        graph = json.loads(result.stdout)
        selected = r84.resolve(graph, contract['validation_only_modules'], resolver)
        write(reports / 'r86-actual-outputs.json', {'runtime_candidates': [], 'validation_only': selected})
        for row in selected:
            action_sources = row['expected_sources'] + ([HEADER] if row['module_name'] == 'bq27z561' else [])
            action = shared.action_chain(graph, action_sources, row['output'])
            action['workspace_source_pins'] = {name: pin(safe(root, name).read_bytes())
                                               for name in action_sources}
            write(reports / ('r86-action-' + row['module_name'] + '.json'), action)
        plan = {'kconfig': bazel + ['build'] + options + ['//vendor/qcom/sm8850:kconfig.msm.generated'],
                'config': bazel + ['build'] + options + ['//vendor/qcom/sm8850:canoe_perf_config'],
                'validation_build': bazel + ['build'] + options + build_targets}
        write(reports / 'r86-commands.json', plan)
        logged(plan['kconfig'], 'kconfig-build')
        logged(plan['config'], 'external-config-build')
        write(reports / 'r86-effective-bq-config.json', verify_effective_bq_config(root, graph, selected))
        status['phase'] = 'compile_inactive_47_module_closure'
        write(status_path, status)
        logged(plan['validation_build'], 'validation-build')
        query = bazel + ['cquery'] + options + ['--output=files', 'deps(set(' + ' '.join(build_targets) + '))']
        result = subprocess.run(query, cwd=root, text=True, capture_output=True)
        (reports / 'r86-validation-cquery.txt').write_text(result.stdout)
        (reports / 'r86-validation-cquery.log').write_text(result.stderr)
        require(result.returncode == 0, 'Compiled-output cquery failed')
        write(reports / 'r86-all-postbuild-postimages.json',
              verify_postimages(root, repo, pc, parent_inputs, r84, route))
        write(reports / 'r86-source-postbuild.json', apply(root, route, verify=True))
        final_config = verify_effective_bq_config(root, graph, selected)
        write(reports / 'r86-bq-config-postbuild.json', final_config)
        final_config = dict(final_config, workspace_root=str(root))
        built = shared.collect_outputs(root, output, contract, selected, result.stdout.splitlines(), r18)
        write(reports / 'r86-collected-validation.json', built)
        status.update(validation_compiled=True, success=True,
                      phase='compiled_inactive_closure_not_runtime_approved',
                      finished_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
        write(status_path, status)
        finalize(output, route, reports, status, final_config)
    except Exception as error:
        status['success'] = False
        status['phase'] = 'failed'
        status['error'] = str(error)
        print('R86 STOP:', error, file=sys.stderr)
    finally:
        if not status['success']:
            status['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        write(status_path, status)
    return 0 if status['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
