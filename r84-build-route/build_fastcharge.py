#!/usr/bin/env python3
"""Compile R84 ADC/gauge prerequisites and a separate inactive MCA source closure."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from apply_fastcharge import BASE_COMMIT, WRITES, apply, pin, require, safe, source_contract

PARENT = 'r83-build-route/power-contract.json'
PARENT_SHA = 'aabf43d239c1be0368aefc59bd88bf5ea46c5dfd1bfa193dcdf1adc27eb290a5'
CANDIDATES = {'myron_bq_readonly', 'qcom_spmi_adc5_gen3', 'qcom_vadc_common'}
SCOPE = 'r61-build-route/runtime-closure-scope.json'


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def expected_postimages(repo, parent_inputs, pc):
    expected = parent_inputs.inherited_postimages(repo)
    expected.update({row['destination']: row['after_sha256'] for row in pc['writes']})
    for filename in ('SOURCE-CONTRACT.json', 'VALIDATION-SOURCE-CONTRACT.json'):
        prior = json.loads((repo / 'r83-build-route' / filename).read_text())
        for row in prior['writes']:
            require(expected.get(row['path']) == row['before']['sha256'], 'R83 ancestry source mismatch')
            expected[row['path']] = row['after']['sha256']
        for row in prior['read_only_guards']:
            digest = row['expected']['sha256']
            require(row['path'] not in expected or expected[row['path']] == digest, 'R83 guard disagrees with inherited source')
            expected[row['path']] = digest
    return expected


def check(repo):
    route = repo / 'r84-build-route'
    c = json.loads((route / 'fastcharge-contract.json').read_text())
    require(c.get('schema') == 1 and c.get('compile_only') is True and c.get('flashable') is False,
            'R84 compile-only contract required')
    require(c.get('base_commit') == BASE_COMMIT and c.get('parent_contract') == PARENT and
            c.get('parent_contract_sha256') == PARENT_SHA, 'Wrong R84 ancestor')
    require(pin((repo / PARENT).read_bytes())['sha256'] == PARENT_SHA, 'R83 frozen preparation changed')
    sys.path.insert(0, str(repo / 'r83-build-route'))
    r83 = load('r84_frozen_r83', repo / 'r83-build-route/build_power.py')
    previous, pc, parent_inputs = r83.check(repo)
    for key in ('baseline_image_sha256', 'baseline_kernel_release', 'sources_lock_sha256', 'git_heads', 'core_targets'):
        require(c.get(key) == previous[key], 'Inherited source/core preparation changed: ' + key)
    rows = c['locked_files']
    names = [r['path'] for r in rows]
    actual = {str(p.relative_to(repo)) for p in route.rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.name != 'fastcharge-contract.json'}
    require(len(names) == len(set(names)) and set(names) == actual, 'R84 inventory changed')
    for row in rows:
        f = safe(repo, row['path'])
        require(f.resolve().is_relative_to(route.resolve()) and pin(f.read_bytes()) == {k: row[k] for k in ('bytes', 'sha256')},
                'R84 locked input changed: ' + row['path'])
    selection = json.loads((route / 'MODULE-SELECTION.json').read_text())
    require(c['modules'] == selection['candidate_modules'] and c['validation_only_modules'] == selection['validation_only_modules'],
            'Module selection disagrees with frozen contract')
    require(c['runtime_candidate_module_names'] == sorted(CANDIDATES) and
            {m['module_name'] for m in c['modules']} == CANDIDATES and len(c['modules']) == 3, 'Wrong candidate scope')
    scope = json.loads((repo / SCOPE).read_text())
    require(c.get('validation_scope') == SCOPE and c.get('validation_scope_sha256') ==
            pin((repo / SCOPE).read_bytes())['sha256'], 'Inactive source closure is not pinned')
    declared = [{k: m[k] for k in ('target', 'module_name', 'expected_sources')} for m in scope['modules']]
    require(c['validation_only_modules'] == declared and len(declared) == 47, 'Exactly the declared 47-module source closure is required')
    targets = [m['target'] for m in c['modules'] + declared]
    require(len(targets) == len(set(targets)) == 50, 'Duplicate build targets')
    require(c['full_charging_control_enabled'] is False and c['validation_runtime_candidate_module_names'] == [] and
            c.get('validation_activation_allowed') is False,
            'Inactive full stack must never become runtime candidates')
    source = source_contract(route)
    require(source.get('preparation_parent_contract_sha256') == PARENT_SHA, 'Source overlay preparation parent is not pinned')
    expected = expected_postimages(repo, parent_inputs, pc)
    for row in source['writes']:
        require(expected.get(row['path']) == row['before']['sha256'], 'R84 overlay does not extend exact prepared R83 source: ' + row['path'])
    require(WRITES <= {s for m in c['modules'] + declared for s in m['expected_sources']}, 'Every changed source must feed a selected action')
    return c, previous, pc, parent_inputs, r83


def verify_postimages(root, repo, pc, parent_inputs, route):
    expected = expected_postimages(repo, parent_inputs, pc)
    source = source_contract(route)
    for row in source['read_only_guards']:
        digest = row['expected']['sha256']
        require(row['path'] not in expected or expected[row['path']] == digest, 'R84 source guard disagrees with ancestry')
        expected[row['path']] = digest
    for row in source['writes']:
        require(expected.get(row['path']) == row['before']['sha256'], 'R84 postimage ancestor mismatch')
        expected[row['path']] = row['after']['sha256']
    for relative, digest in expected.items():
        require(pin(safe(root, relative).read_bytes())['sha256'] == digest, 'Integrated source changed: ' + relative)
    return {'schema': 1, 'status': 'PASS_ALL_INHERITED_AND_R84_POSTIMAGES', 'checked_destinations': len(expected),
            'exact_overlays': sorted(WRITES), 'unchanged_R83_MCA_source': True}


def resolve(graph, records, resolver):
    selected = []
    for row in records:
        request = dict(row)
        if 'output_basename' in row:
            request['module_name'] = row['output_basename'][:-3]
        result = resolver.resolve(graph, request)
        selected.append(dict(result, module_name=row['module_name']))
    return selected


def mark_role(output, candidate):
    policy = {'role': 'candidate_compile_proof' if candidate else 'validation_only', 'activation_allowed': False,
              'runtime_candidate_module_names': sorted(CANDIDATES) if candidate else [],
              'full_charging_control_enabled': False, 'runtime_abi_compatible': 'NOT_YET_VALIDATED'}
    for name in ('artifact-manifest.json', 'module-inventory.json', 'module-identity.json'):
        p = output / name
        d = json.loads(p.read_text()); d.update(policy); write(p, d)
    return policy


def finalize(output, route, reports, status, candidate, required):
    shutil.copy2(route / 'fastcharge-contract.json', output / 'fastcharge-contract.json')
    shutil.copytree(route, output / 'source/r84-build-route', ignore=shutil.ignore_patterns('__pycache__'))
    dest = output / 'reports'; dest.mkdir()
    for p in reports.rglob('*'):
        if p.is_file() and (p.name.startswith('r84-') or 'r84-host' in p.parts) and p.suffix in ('.json', '.log', '.txt'):
            t = dest / p.relative_to(reports); t.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p, t)
    policy = mark_role(output, candidate)
    write(output / 'artifact-lock.json', {'schema': 1, 'compile_only': True, **policy, 'files': [
        {'file': str(p.relative_to(output)), **pin(p.read_bytes())}
        for p in sorted(output.rglob('*')) if p.is_file()]})
    write(output / ('candidate-complete.json' if candidate else 'validation-complete.json'), {
        'schema': 1, 'compile_only': True, 'flashable': False, **policy,
        'required_module_count': required, 'candidate_compile_success': status['candidate_compiled'],
        'full_validation_success': status['validation_compiled'],
        'source_contract_sha256': status['source_contract_sha256'],
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
        c, _, _, _, _ = check(repo)
        print(json.dumps({'status': 'PASS_R84_FROZEN_INPUTS', 'candidate_modules': c['runtime_candidate_module_names'],
                          'validation_only_count': len(c['validation_only_modules']), 'locked_inputs': len(c['locked_files'])}))
        return 0
    require(all(getattr(args, n) is not None for n in ('workspace', 'package', 'baseline', 'r18')), 'Four build paths required')
    root, package, baseline, r18 = [getattr(args, n).resolve() for n in ('workspace', 'package', 'baseline', 'r18')]
    route = repo / 'r84-build-route'; reports = root / 'integration-reports'
    output = root / 'integration-artifacts/r84-fastcharge-candidates'
    validation_output = root / 'integration-artifacts/r84-mca-validation-only'
    status_path = reports / 'r84-status.json'
    status = {'schema': 1, 'success': False, 'candidate_compiled': False, 'validation_compiled': False,
              'compile_only': True, 'flashable': False, 'hardware_tested': False, 'full_charging_control_enabled': False,
              'github': {k: os.environ.get(k, '') for k in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')},
              'phase': 'preflight', 'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    write(status_path, status)
    try:
        require(1 <= args.jobs <= 4 and args.ram_mb >= 2048, 'Invalid resource budget')
        require(all(not p.exists() and not p.is_symlink() for p in (output, validation_output)), 'Fresh artifact paths required')
        c, previous, pc, parent_inputs, r83 = check(repo)
        status['source_contract_sha256'] = pin((route / 'fastcharge-contract.json').read_bytes())['sha256']
        parent, multimedia = parent_inputs.parent(repo)
        thermal, thermal_contract = parent.parent(repo)
        inherited = json.loads((repo / thermal_contract['base_contract']).read_text())
        sys.path.insert(0, str(repo / 'r61-build-route'))
        shared = load('r84_shared', repo / 'r61-build-route/targeted_battery_build.py')
        resolver = load('r84_resolver', repo / 'r78-build-route/resolve_outputs.py')
        old = load('r84_r18', r18 / 'boot_build.py'); status['r18_bundle_lock_sha256'] = old.verify_bundle()
        helper = load('r84_driver', baseline / 'drivers/driver_check.py')
        runner_data, status['baseline_runner'] = helper.verify_bundle(baseline, package / 'build_platform.py')
        require(pin((package / 'sources.lock.json').read_bytes())['sha256'] == c['sources_lock_sha256'], 'Source lock changed')
        bazel, options = helper.runner_build_configuration(runner_data, root, args.jobs, args.ram_mb)
        options = list(options) + ['--nokeep_going']
        runner = load('r84_platform', package / 'build_platform.py')
        def logged(command, name):
            runner.logged(command, root, reports / ('r84-' + name + '.log'))
        status['phase'] = 'prepare_unchanged_R83_sources'; write(status_path, status)
        logged([sys.executable, str(package / 'prepare_workspace.py'), '--workspace', str(root)], 'prepare')
        logged([sys.executable, str(baseline / 'run_r12.py'), 'apply', '--workspace', str(root), '--stage', 'soc'], 'r13-apply')
        helper.verify_applied_writes(baseline, root)
        hardware = json.loads((repo / inherited['prerequisite_contract']).read_text())
        for name, sc in [('r60', hardware), ('r61', inherited)]:
            command = [sys.executable, str(repo / sc['integration']['script']), '--workspace', str(root)]
            logged(command, name + '-apply'); logged(command + ['--check'], name + '-check')
            shared.locked_workspace(root, sc['workspace_files'])
        from apply_thermal import apply as apply_thermal
        from apply_multimedia import apply as apply_multimedia
        from apply_repairs import apply as apply_repairs, verify_applied
        for name, operation, contract in [('thermal', apply_thermal, thermal_contract), ('multimedia', apply_multimedia, multimedia), ('repairs', apply_repairs, pc)]:
            write(reports / ('r84-parent-' + name + '-apply.json'), operation(root, repo, contract))
            write(reports / ('r84-parent-' + name + '-check.json'), operation(root, repo, contract, verify=True))
        write(reports / 'r84-parent-r79-postimages.json', verify_applied(root, repo, pc))
        power = load('r84_r83_power', repo / 'r83-build-route/apply_power.py')
        write(reports / 'r84-parent-r83-power.json', power.apply(root, repo / 'r83-build-route'))
        validation = load('r84_r83_validation', repo / 'r83-build-route/validation_only.py')
        write(reports / 'r84-parent-r83-validation.json', validation.prepare(root, repo / 'r83-build-route'))
        write(reports / 'r84-parent-r83-postimages.json', r83.verify_r83_postimages(root, repo, pc, parent_inputs, repo / 'r83-build-route'))
        write(reports / 'r84-source-apply.json', apply(root, route))
        write(reports / 'r84-source-check.json', apply(root, route, verify=True))
        logged([sys.executable, str(route / 'test_source.py'), '--workspace', str(root), '--output', str(reports / 'r84-host')], 'production-source-tests')
        write(reports / 'r84-all-prebuild-postimages.json', verify_postimages(root, repo, pc, parent_inputs, route))
        runner.build_targets(root, 'soc')
        candidate_targets = [m['target'] for m in c['modules']] + c['core_targets']
        validation_targets = [m['target'] for m in c['validation_only_modules']] + c['core_targets']
        all_module_targets = candidate_targets[:-len(c['core_targets'])] + validation_targets[:-len(c['core_targets'])]
        status['phase'] = 'analyze_all_50_explicit_targets'; write(status_path, status)
        analysis = bazel + ['aquery'] + options + ['--output=jsonproto', '--include_artifacts=true', '--include_commandline=true', 'deps(set(' + ' '.join(all_module_targets) + '))']
        result = subprocess.run(analysis, cwd=root, text=True, capture_output=True)
        (reports / 'r84-aquery.json').write_text(result.stdout); (reports / 'r84-aquery.log').write_text(result.stderr)
        require(result.returncode == 0, 'Actual target aquery failed before core compile')
        graph = json.loads(result.stdout)
        selected = resolve(graph, c['modules'], resolver)
        validation_selected = resolve(graph, c['validation_only_modules'], resolver)
        write(reports / 'r84-actual-outputs.json', {'runtime_candidates': selected, 'validation_only': validation_selected})
        for row in selected + validation_selected:
            write(reports / ('r84-action-' + row['module_name'] + '.json'), shared.action_chain(graph, row['expected_sources'], row['output']))
        plan = {'kconfig': bazel + ['build'] + options + ['//vendor/qcom/sm8850:kconfig.msm.generated'],
                'config': bazel + ['build'] + options + ['//vendor/qcom/sm8850:canoe_perf_config'],
                'candidate_build': bazel + ['build'] + options + candidate_targets,
                'validation_build': bazel + ['build'] + options + validation_targets}
        write(reports / 'r84-commands.json', plan)
        logged(plan['kconfig'], 'kconfig-build'); logged(plan['config'], 'external-config-build')
        write(reports / 'r84-effective-adc-config.json', validation.verify_effective_config(root, graph))
        for candidate, records, targets, outpath, phase in [(True, selected, candidate_targets, output, 'candidate'), (False, validation_selected, validation_targets, validation_output, 'validation')]:
            status['phase'] = 'compile_' + phase; write(status_path, status)
            logged(plan[phase + '_build'], phase + '-build')
            query = bazel + ['cquery'] + options + ['--output=files', 'deps(set(' + ' '.join(targets) + '))']
            result = subprocess.run(query, cwd=root, text=True, capture_output=True)
            (reports / ('r84-' + phase + '-cquery.txt')).write_text(result.stdout)
            (reports / ('r84-' + phase + '-cquery.log')).write_text(result.stderr)
            require(result.returncode == 0, phase + ' cquery failed')
            write(reports / ('r84-all-postbuild-' + phase + '.json'), verify_postimages(root, repo, pc, parent_inputs, route))
            write(reports / ('r84-source-postbuild-' + phase + '.json'), apply(root, route, verify=True))
            write(reports / ('r84-adc-config-postbuild-' + phase + '.json'), validation.verify_effective_config(root, graph))
            built = shared.collect_outputs(root, outpath, c, records, result.stdout.splitlines(), r18)
            write(reports / ('r84-collected-' + phase + '.json'), built)
            status['candidate_compiled' if candidate else 'validation_compiled'] = True
            write(status_path, status)
        status.update(success=True, phase='compiled_candidates_and_inactive_closure_not_runtime_approved')
    except Exception as error:
        status['error'] = str(error); print('R84 STOP:', error, file=sys.stderr)
    finally:
        status['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()); write(status_path, status)
        for candidate, outpath, key, count in [(True, output, 'candidate_compiled', 3), (False, validation_output, 'validation_compiled', 47)]:
            if status[key]:
                finalize(outpath, route, reports, status, candidate, count)
    return 0 if status['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
