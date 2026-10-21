#!/usr/bin/env python3
"""Compile the reviewed R85 full-BQ repair within the inactive 47-module MCA closure."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from apply_bq import BASE_COMMIT, FULL_BQ, PARENT_SHA, WRITES, apply, pin, require, safe, source_contract

PARENT = 'r84-build-route/fastcharge-contract.json'
SCOPE = 'r61-build-route/runtime-closure-scope.json'
FORBIDDEN_TARGETS = {
    '//vendor/qcom/sm8850:canoe_perf/drivers/iio/adc/qcom-spmi-adc5-gen3',
    '//vendor/qcom/sm8850:canoe_perf/drivers/iio/adc/qcom-vadc-common',
    '//vendor/qcom/sm8850:canoe_perf/drivers/power/supply/myron_bq_readonly',
}


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parent_postimages(repo, pc, parent_inputs, r84):
    expected = r84.expected_postimages(repo, parent_inputs, pc)
    previous = r84.source_contract(repo / 'r84-build-route')
    for row in previous['read_only_guards']:
        digest = row['expected']['sha256']
        require(row['path'] not in expected or expected[row['path']] == digest,
                'R84 source guard disagrees with inherited preparation')
        expected[row['path']] = digest
    for row in previous['writes']:
        require(expected.get(row['path']) == row['before']['sha256'], 'R84 postimage ancestry mismatch')
        expected[row['path']] = row['after']['sha256']
    return expected


def check(repo):
    route = repo / 'r85-build-route'
    contract = json.loads((route / 'build-contract.json').read_text())
    require(contract.get('schema') == 1 and contract.get('review_status') == 'FROZEN_REVIEWED_SOURCE' and
            contract.get('compile_only') is True and contract.get('flashable') is False,
            'Frozen R85 compile-only contract required')
    require(contract.get('base_commit') == BASE_COMMIT and contract.get('parent_contract') == PARENT and
            contract.get('parent_contract_sha256') == PARENT_SHA, 'Wrong R85 parent')
    require(pin((repo / PARENT).read_bytes())['sha256'] == PARENT_SHA, 'Frozen R84 contract changed')
    sys.path.insert(0, str(repo / 'r84-build-route'))
    r84 = load('r85_frozen_r84', repo / 'r84-build-route/build_fastcharge.py')
    previous, _, pc, parent_inputs, r83 = r84.check(repo)
    for key in ('baseline_image_sha256', 'baseline_kernel_release', 'sources_lock_sha256', 'git_heads', 'core_targets'):
        require(contract.get(key) == previous[key], 'Inherited source/core preparation changed: ' + key)
    rows = contract['locked_files']
    names = [row['path'] for row in rows]
    actual = {str(path.relative_to(repo)) for path in route.rglob('*')
              if path.is_file() and '__pycache__' not in path.parts and path.name != 'build-contract.json'}
    require(len(names) == len(set(names)) and set(names) == actual, 'R85 locked inventory changed')
    for row in rows:
        path = safe(repo, row['path'])
        require(path.resolve().is_relative_to(route.resolve()) and
                pin(path.read_bytes()) == {key: row[key] for key in ('bytes', 'sha256')},
                'R85 locked input changed: ' + row['path'])
    require(contract.get('validation_scope') == SCOPE and contract.get('validation_scope_sha256') ==
            pin((repo / SCOPE).read_bytes())['sha256'], 'Inactive source closure scope changed')
    declared = [{key: module[key] for key in ('target', 'module_name', 'expected_sources')}
                for module in json.loads((repo / SCOPE).read_text())['modules']]
    require(contract.get('validation_only_modules') == declared and len(declared) == 47,
            'Exactly the frozen 47-module MCA closure is required')
    targets = [row['target'] for row in declared]
    require(len(set(targets)) == 47 and not FORBIDDEN_TARGETS.intersection(targets),
            'Duplicate targets or redundant R84 ADC/gauge candidate builds')
    require(contract.get('modules') == [] and contract.get('runtime_candidate_module_names') == [] and
            contract.get('full_charging_control_enabled') is False and contract.get('activation_allowed') is False,
            'All R85 full-MCA outputs must stay inactive')
    source = source_contract(route)
    expected = parent_postimages(repo, pc, parent_inputs, r84)
    for row in source['read_only_guards']:
        require(row['path'] not in expected or expected[row['path']] == row['expected']['sha256'],
                'R85 source guard disagrees with frozen parent: ' + row['path'])
    for row in source['writes']:
        require(expected.get(row['path']) == row['before']['sha256'],
                'R85 overlay does not extend the exact prepared R84 source: ' + row['path'])
    require(WRITES <= {name for row in declared for name in row['expected_sources']},
            'Changed source does not feed a selected build action')
    require(contract.get('source_contract') == pin((route / 'SOURCE-CONTRACT.json').read_bytes()),
            'Build contract does not bind exact source contract')
    return contract, previous, pc, parent_inputs, r83, r84


def verify_postimages(root, repo, pc, parent_inputs, r84, route):
    expected = parent_postimages(repo, pc, parent_inputs, r84)
    source = source_contract(route)
    for row in source['read_only_guards']:
        digest = row['expected']['sha256']
        require(row['path'] not in expected or expected[row['path']] == digest,
                'R85 source guard disagrees with ancestry')
        expected[row['path']] = digest
    for row in source['writes']:
        require(expected.get(row['path']) == row['before']['sha256'], 'R85 source ancestor mismatch')
        expected[row['path']] = row['after']['sha256']
    for relative, digest in expected.items():
        require(pin(safe(root, relative).read_bytes())['sha256'] == digest,
                'Integrated source changed: ' + relative)
    return {'schema': 1, 'status': 'PASS_ALL_INHERITED_AND_R85_POSTIMAGES',
            'checked_destinations': len(expected), 'exact_overlays': sorted(WRITES),
            'R84_ADC_gauge_USB_and_R83_MCA_sources_unchanged': True}


def verify_effective_bq_config(root, graph, modules):
    """Bind the real BQ compile action to its generated external-module config."""
    labels = {str(row['id']): row['label'] for row in graph.get('targets', [])}
    fragments = {str(row['id']): row for row in graph.get('pathFragments', [])}
    def fragment_path(key, seen=None):
        key = str(key)
        seen = set() if seen is None else seen
        require(key in fragments and key not in seen, 'Invalid config artifact path')
        seen.add(key)
        row = fragments[key]
        parent = str(row.get('parentId', '0'))
        value = (fragment_path(parent, seen) + '/' if parent not in ('', '0') else '') + row['label']
        seen.remove(key)
        return value
    artifacts = {str(row['id']): row.get('execPath') or fragment_path(row['pathFragmentId'])
                 for row in graph.get('artifacts', [])}
    dep_sets = {str(row['id']): row for row in graph.get('depSetOfFiles', [])}
    def consumed(keys, seen=None):
        seen = set() if seen is None else seen
        found = set()
        for key in keys:
            key = str(key)
            require(key in dep_sets and key not in seen, 'Invalid config depset')
            seen.add(key)
            row = dep_sets[key]
            found.update(str(value) for value in row.get('directArtifactIds', []))
            found.update(consumed(row.get('transitiveDepSetIds', []), seen))
            seen.remove(key)
        return found
    config_target = '//vendor/qcom/sm8850:canoe_perf_config'
    config_actions = [action for action in graph.get('actions', [])
                      if labels.get(str(action.get('targetId'))) == config_target and
                      action.get('mnemonic') == 'DdkConfig']
    require(len(config_actions) == 1, 'Expected one real external-module config action')
    config_action = config_actions[0]
    tree = 'bazel-out/aarch64-fastbuild/bin/vendor/qcom/sm8850/canoe_perf_config/out_dir'
    tree_ids = [str(key) for key in config_action.get('outputIds', []) if artifacts[str(key)] == tree]
    require(len(tree_ids) == 1, 'Actual config action does not own reviewed config tree')
    bq_modules = [row for row in modules if row['module_name'] == 'bq27z561']
    require(len(bq_modules) == 1 and bq_modules[0]['expected_sources'] == [FULL_BQ], 'Exact full-BQ action scope')
    bq_target = bq_modules[0]['target']
    bq_actions = [action for action in graph.get('actions', [])
                  if labels.get(str(action.get('targetId'))) == bq_target and action.get('mnemonic') == 'KernelModule']
    require(len(bq_actions) == 1, 'Missing real full-BQ compile action')
    bq_action = bq_actions[0]
    inputs = consumed(bq_action.get('inputDepSetIds', []))
    require(tree_ids[0] in inputs, 'Full-BQ compile does not consume reviewed config tree')
    own_actions = [action for action in graph.get('actions', [])
                   if labels.get(str(action.get('targetId'))) == bq_target + '_config']
    require(not any(action.get('mnemonic') == 'DdkConfig' for action in own_actions),
            'Unexpected per-module full-BQ config override')
    setup = [str(key) for action in own_actions for key in action.get('outputIds', [])
             if artifacts[str(key)].endswith('_config_setup.sh')]
    require(len(setup) == 1 and setup[0] in inputs and
            artifacts[setup[0]] in '\n'.join(bq_action.get('arguments', [])),
            'Full-BQ target config setup is not consumed by its compiler command')
    relative = tree + '/.config'
    require(relative in '\n'.join(config_action.get('arguments', [])), 'Config action does not materialize .config')
    # bazel-out is an expected Bazel-owned symlink. This fixed graph-proven
    # output path is read only; source-overlay destinations remain symlink-free.
    data = (root / relative).read_bytes()
    settings = dict(line.split('=', 1) for line in data.decode().splitlines()
                    if line.startswith('CONFIG_') and '=' in line)
    require(settings.get('CONFIG_MYRON_IC_FIRMWARE_PROGRAMMING', 'n') == 'n',
            'IC firmware programming must remain disabled')
    return {'schema': 1, 'status': 'PASS_ACTUAL_BQ_CONFIG', 'config_path': relative, **pin(data),
            'target_owned_setup': artifacts[setup[0]], 'config_tree_consumed_by_actual_bq_action': True,
            'settings': {'CONFIG_MYRON_IC_FIRMWARE_PROGRAMMING': settings.get('CONFIG_MYRON_IC_FIRMWARE_PROGRAMMING', 'n')},
            'activation_allowed': False}


def finalize(output, route, reports, status, config):
    policy = {'role': 'validation_only', 'compile_only': True, 'flashable': False,
              'activation_allowed': False, 'runtime_candidate_module_names': [],
              'full_charging_control_enabled': False, 'runtime_abi_compatible': 'NOT_YET_VALIDATED'}
    for name in ('artifact-manifest.json', 'module-inventory.json', 'module-identity.json'):
        path = output / name
        record = json.loads(path.read_text())
        record.update(policy)
        write(path, record)
    inventory = json.loads((output / 'module-inventory.json').read_text())
    require(inventory['module_count'] == 47, 'Final inventory must contain all47 inactive modules')
    shutil.copy2(route / 'build-contract.json', output / 'build-contract.json')
    shutil.copytree(route, output / 'source/r85-build-route', ignore=shutil.ignore_patterns('__pycache__'))
    compiled_source = Path(config['workspace_root']) / FULL_BQ
    expected_source = source_contract(route)['writes'][0]['after']
    require(pin(compiled_source.read_bytes()) == expected_source,
            'Actual compiled full-BQ postimage changed before artifact finalization')
    compiled_source.read_bytes().decode('utf-8')
    source_destination = output / 'compiled-source/bq27z561.c'
    source_destination.parent.mkdir()
    shutil.copy2(compiled_source, source_destination)
    destination = output / 'reports'
    destination.mkdir()
    for path in reports.rglob('*'):
        if path.is_file() and (path.name.startswith('r85-') or 'r85-host' in path.parts) and path.suffix in ('.json', '.log', '.txt'):
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
    write(output / 'validation-complete.json', {'schema': 1, **policy,
        'required_module_count': 47, 'full_validation_success': True,
        'build_contract_sha256': status['build_contract_sha256'],
        'source_contract_sha256': status['source_contract_sha256'],
        'compiled_source': {'file': 'compiled-source/bq27z561.c', **expected_source},
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
        contract, _, _, _, _, _ = check(repo)
        print(json.dumps({'status': 'PASS_R85_FROZEN_INPUTS', 'runtime_candidates': [],
                          'validation_only_count': 47, 'locked_inputs': len(contract['locked_files'])}))
        return 0
    require(all(getattr(args, name) is not None for name in ('workspace', 'package', 'baseline', 'r18')),
            'Four build paths required')
    root, package, baseline, r18 = [getattr(args, name).resolve() for name in ('workspace', 'package', 'baseline', 'r18')]
    route = repo / 'r85-build-route'
    reports = root / 'integration-reports'
    output = root / 'integration-artifacts/r85-mca-validation-only'
    status_path = reports / 'r85-status.json'
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
        contract, _, pc, parent_inputs, r83, r84 = check(repo)
        status['build_contract_sha256'] = pin((route / 'build-contract.json').read_bytes())['sha256']
        status['source_contract_sha256'] = pin((route / 'SOURCE-CONTRACT.json').read_bytes())['sha256']
        parent, multimedia = parent_inputs.parent(repo)
        thermal, thermal_contract = parent.parent(repo)
        inherited = json.loads((repo / thermal_contract['base_contract']).read_text())
        sys.path.insert(0, str(repo / 'r61-build-route'))
        shared = load('r85_shared', repo / 'r61-build-route/targeted_battery_build.py')
        resolver = load('r85_resolver', repo / 'r78-build-route/resolve_outputs.py')
        old = load('r85_r18', r18 / 'boot_build.py')
        status['r18_bundle_lock_sha256'] = old.verify_bundle()
        helper = load('r85_driver', baseline / 'drivers/driver_check.py')
        runner_data, status['baseline_runner'] = helper.verify_bundle(baseline, package / 'build_platform.py')
        require(pin((package / 'sources.lock.json').read_bytes())['sha256'] == contract['sources_lock_sha256'],
                'Source lock changed')
        bazel, options = helper.runner_build_configuration(runner_data, root, args.jobs, args.ram_mb)
        options = list(options) + ['--nokeep_going']
        runner = load('r85_platform', package / 'build_platform.py')
        def logged(command, name):
            runner.logged(command, root, reports / ('r85-' + name + '.log'))
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
            write(reports / ('r85-parent-' + name + '-apply.json'), operation(root, repo, source))
            write(reports / ('r85-parent-' + name + '-check.json'), operation(root, repo, source, verify=True))
        write(reports / 'r85-parent-r79-postimages.json', verify_applied(root, repo, pc))
        power = load('r85_r83_power', repo / 'r83-build-route/apply_power.py')
        write(reports / 'r85-parent-r83-power.json', power.apply(root, repo / 'r83-build-route'))
        validation = load('r85_r83_validation', repo / 'r83-build-route/validation_only.py')
        write(reports / 'r85-parent-r83-validation.json', validation.prepare(root, repo / 'r83-build-route'))
        write(reports / 'r85-parent-r83-postimages.json',
              r83.verify_r83_postimages(root, repo, pc, parent_inputs, repo / 'r83-build-route'))
        write(reports / 'r85-parent-r84-source-apply.json', r84.apply(root, repo / 'r84-build-route'))
        write(reports / 'r85-parent-r84-source-check.json', r84.apply(root, repo / 'r84-build-route', verify=True))
        write(reports / 'r85-parent-r84-postimages.json',
              r84.verify_postimages(root, repo, pc, parent_inputs, repo / 'r84-build-route'))
        write(reports / 'r85-source-apply.json', apply(root, route))
        write(reports / 'r85-source-check.json', apply(root, route, verify=True))
        logged([sys.executable, str(route / 'test_source.py'), '--workspace', str(root),
                '--output', str(reports / 'r85-host')], 'production-source-tests')
        write(reports / 'r85-all-prebuild-postimages.json',
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
        (reports / 'r85-aquery.json').write_text(result.stdout)
        (reports / 'r85-aquery.log').write_text(result.stderr)
        require(result.returncode == 0, 'Actual target aquery failed before compile')
        graph = json.loads(result.stdout)
        selected = r84.resolve(graph, contract['validation_only_modules'], resolver)
        write(reports / 'r85-actual-outputs.json', {'runtime_candidates': [], 'validation_only': selected})
        for row in selected:
            action = shared.action_chain(graph, row['expected_sources'], row['output'])
            action['workspace_source_pins'] = {name: pin(safe(root, name).read_bytes())
                                               for name in row['expected_sources']}
            write(reports / ('r85-action-' + row['module_name'] + '.json'), action)
        plan = {'kconfig': bazel + ['build'] + options + ['//vendor/qcom/sm8850:kconfig.msm.generated'],
                'config': bazel + ['build'] + options + ['//vendor/qcom/sm8850:canoe_perf_config'],
                'validation_build': bazel + ['build'] + options + build_targets}
        write(reports / 'r85-commands.json', plan)
        logged(plan['kconfig'], 'kconfig-build')
        logged(plan['config'], 'external-config-build')
        write(reports / 'r85-effective-bq-config.json', verify_effective_bq_config(root, graph, selected))
        status['phase'] = 'compile_inactive_47_module_closure'
        write(status_path, status)
        logged(plan['validation_build'], 'validation-build')
        query = bazel + ['cquery'] + options + ['--output=files', 'deps(set(' + ' '.join(build_targets) + '))']
        result = subprocess.run(query, cwd=root, text=True, capture_output=True)
        (reports / 'r85-validation-cquery.txt').write_text(result.stdout)
        (reports / 'r85-validation-cquery.log').write_text(result.stderr)
        require(result.returncode == 0, 'Compiled-output cquery failed')
        write(reports / 'r85-all-postbuild-postimages.json',
              verify_postimages(root, repo, pc, parent_inputs, r84, route))
        write(reports / 'r85-source-postbuild.json', apply(root, route, verify=True))
        final_config = verify_effective_bq_config(root, graph, selected)
        write(reports / 'r85-bq-config-postbuild.json', final_config)
        final_config = dict(final_config, workspace_root=str(root))
        built = shared.collect_outputs(root, output, contract, selected, result.stdout.splitlines(), r18)
        write(reports / 'r85-collected-validation.json', built)
        status.update(validation_compiled=True, success=True,
                      phase='compiled_inactive_closure_not_runtime_approved',
                      finished_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
        write(status_path, status)
        finalize(output, route, reports, status, final_config)
    except Exception as error:
        status['success'] = False
        status['phase'] = 'failed'
        status['error'] = str(error)
        print('R85 STOP:', error, file=sys.stderr)
    finally:
        if not status['success']:
            status['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        write(status_path, status)
    return 0 if status['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
