#!/usr/bin/env python3
"""Compile the R83 Myron bounded USB cache candidate using the frozen R79 preparation.

Only the MCA target and its mandatory build dependencies are requested. This
route never creates a flashable image or approves installed-kernel ABI mixing.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import time

PARENT = 'r79-build-route/repair-contract.json'
PARENT_SHA = 'aabb37375d33dfe9ae1bf9a86e7a3ce4602bd67f06855709b046fa493d744cc2'
TARGET = '//vendor/qcom/sm8850:canoe_perf/drivers/power/supply/myron_mca_readonly/myron_mca_readonly'
MODULE = 'myron_mca_readonly'
BASE_COMMIT = '45405ec4b75ac71c60f3178d1be24db312fae3ff'
SOURCE_PREFIX = 'vendor/qcom/sm8850/drivers/power/supply/myron_mca_readonly/'
TRANSPORT_TARGET = '//vendor/qcom/sm8850:canoe_perf/drivers/soc/qcom/qti_pmic_glink'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(repo):
    route = repo / 'r83-build-route'
    c = json.loads((route / 'power-contract.json').read_text())
    require(c.get('schema') == 1 and c.get('compile_only') is True and c.get('flashable') is False,
            'Compile-only contract required')
    require(c.get('parent_contract') == PARENT and c.get('parent_contract_sha256') == PARENT_SHA,
            'Wrong parent contract')
    require(c.get('base_commit') == BASE_COMMIT and c.get('runtime_candidate_module_names') == [MODULE],
            'Reviewed base revision and MCA-only runtime selection are mandatory')
    require(sha((repo / PARENT).read_bytes()) == PARENT_SHA, 'Frozen R79 preparation changed')
    pc = json.loads((repo / PARENT).read_text())
    for key in ('baseline_image_sha256', 'baseline_kernel_release', 'sources_lock_sha256', 'git_heads', 'core_targets'):
        require(c.get(key) == pc[key], 'Inherited build preparation changed: ' + key)
    modules = c.get('modules', [])
    require(len(modules) == 1 and modules[0].get('target') == TARGET and modules[0].get('module_name') == MODULE,
            'Unexpected MCA selection')
    sources = modules[0].get('expected_sources', [])
    require(sources == [SOURCE_PREFIX + 'myron_mca_readonly.c'], 'MCA source binding changed')
    require(sources and len(sources) == len(set(sources)) and
            all(s.startswith(SOURCE_PREFIX) and s.endswith('.c') and '..' not in PurePosixPath(s).parts for s in sources),
            'Missing or unsafe patched source bindings')
    source_contract = json.loads((route / 'SOURCE-CONTRACT.json').read_text())
    require(source_contract.get('source_repository') == 'yuwenhua653/oppo_oplus_realme_sm8850' and
            source_contract.get('source_commit') == c['base_commit'] and
            source_contract.get('preparation_parent_contract_sha256') == PARENT_SHA,
            'MCA patch does not extend the locked R79 preparation at the reviewed repository revision')
    writes = source_contract.get('writes', [])
    require(len(writes) == 1 and {r['path'] for r in writes} == set(sources),
            'Every patched C file must feed the sole selected MCA output')
    require(all(r['path'] == SOURCE_PREFIX + 'myron_mca_readonly.c' for r in writes),
            'MCA patch scope changed')
    old_source = repo / 'r75-build-route/payload/drivers/power/supply/myron_mca_readonly/myron_mca_readonly.c'
    old_data = old_source.read_bytes()
    require({'bytes': len(old_data), 'sha256': sha(old_data)} == writes[0]['before'],
            'Patch preimage is not the exact retained R75 client source')
    validation = load('r83_validation_inputs', route / 'validation_only.py')
    validation.check_contract(route, c)
    rows = c['locked_files']
    names = [row['path'] for row in rows]
    actual = {str(p.relative_to(repo)) for p in route.rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.name != 'power-contract.json'}
    require(len(names) == len(set(names)) and set(names) == actual, 'R83 input inventory changed')
    for row in rows:
        relative = PurePosixPath(row['path'])
        require(not relative.is_absolute() and '..' not in relative.parts, 'Unsafe locked path')
        p = repo / relative
        require(not p.is_symlink() and p.resolve().is_relative_to(route.resolve()), 'Redirected locked input')
        data = p.read_bytes()
        require(len(data) == row['bytes'] and sha(data) == row['sha256'], 'Changed locked input: ' + row['path'])
    sys.path.insert(0, str(repo / 'r79-build-route'))
    parent_inputs = load('r83_r79_inputs', repo / 'r79-build-route/r79_inputs.py')
    parent_inputs.check(repo, pc)
    return c, pc, parent_inputs


def verify_r83_postimages(workspace, repo, parent_contract, parent_inputs, route):
    expected = parent_inputs.inherited_postimages(repo)
    expected.update({row['destination']: row['after_sha256'] for row in parent_contract['writes']})
    replacements = []
    for name in ('SOURCE-CONTRACT.json', 'VALIDATION-SOURCE-CONTRACT.json'):
        source = json.loads((route / name).read_text())
        for row in source['writes']:
            require(expected.get(row['path']) == row['before']['sha256'], 'R83 overlay does not extend exact inherited postimage: ' + row['path'])
            expected[row['path']] = row['after']['sha256']
            replacements.append(row['path'])
    require(len(replacements) == 2 and len(set(replacements)) == 2, 'Exactly two independently scoped R83 source replacements required')
    for relative, digest in expected.items():
        path = parent_inputs.safe(workspace, relative)
        require(sha(path.read_bytes()) == digest, 'Integrated R83 postimage changed: ' + relative)
    return {'schema': 1, 'status': 'PASS_ALL_INHERITED_AND_R83_POSTIMAGES', 'checked_destinations': len(expected), 'exact_overlays': replacements}


def verify_transport_dependency(graph):
    labels = {str(r['id']): r['label'] for r in graph.get('targets', [])}
    require(TRANSPORT_TARGET in labels.values(), 'MCA lacks the actual QTI transport dependency')
    actions = [a for a in graph.get('actions', [])
               if labels.get(str(a.get('targetId'))) == TARGET and
               a.get('mnemonic') == 'KernelModule']
    require(len(actions) == 1, 'Expected one MCA compile action')
    command = '\n'.join(actions[0].get('arguments', []))
    provider = ('bazel-out/aarch64-fastbuild/bin/vendor/qcom/sm8850/canoe_perf/'
                'drivers/soc/qcom/qti_pmic_glink/canoe_perf/drivers/soc/qcom/qti_pmic_glink_Module.symvers')
    require(provider in command, 'MCA compile action does not stage QTI transport Module.symvers')
    return {'schema': 1, 'status': 'PASS_TRANSPORT_COMPILE_DEPENDENCY',
            'consumer_target': TARGET, 'provider_target': TRANSPORT_TARGET,
            'staged_provider_symvers': provider,
            'runtime_provider_replacement_allowed': False}


def verify_built_mca(root, module, output):
    from elf_contract import parse_elf
    data = (root / module['output']).read_bytes()
    client = parse_elf(data)
    required = 'pmic_glink_unregister_client_sync'
    require(client['name'] == MODULE, 'Wrong compiled MCA client identity')
    require(required in client['imports'] and required in client['versions'],
            'Client lacks the mandatory synchronous unregister interface')
    require('pmic_glink_unregister_client' not in client['imports'],
            'Unsafe old asynchronous unregister fallback is forbidden')
    require(client['depends'] == ['qti_pmic_glink'], 'Unexpected client module dependency')
    parameters = client['info'].get('parmtype', [])
    require(len(parameters) == 3 and set(parameters) == {
                'enable_readonly:bool', 'enable_power_supply:bool', 'enable_extra_diagnostics:bool'},
            'Compiled client parameter allowlist differs')
    inventory = json.loads((output / 'module-inventory.json').read_text())
    require(inventory['module_count'] == 1 and inventory['modules'][0]['name'] == MODULE,
            'MCA-only KO inventory required')
    return {'schema': 1, 'status': 'PASS_BUILT_MCA_CLIENT_METADATA',
            'required_transport_import': required, 'required_import_crc': hex(client['versions'][required]),
            'module_dependencies': client['depends'], 'boolean_parameters': sorted(parameters),
            'runtime_abi_compatible': 'NOT_YET_VALIDATED'}


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
        c, _, _ = check(repo)
        print(json.dumps({'status': 'PASS_FROZEN_INPUTS', 'selected_target': TARGET,
                          'locked_inputs': len(c['locked_files']), 'flashable': False}))
        return 0
    require(all(getattr(args, n) is not None for n in ('workspace', 'package', 'baseline', 'r18')),
            'All four build paths are required')
    root, package, baseline, r18 = [getattr(args, n).resolve() for n in ('workspace', 'package', 'baseline', 'r18')]
    route = repo / 'r83-build-route'
    reports = root / 'integration-reports'
    output = root / 'integration-artifacts/r83-power-candidate'
    validation_output = root / 'integration-artifacts/r83-validation-only'
    status_path = reports / 'r83-status.json'
    status = {'schema': 1, 'success': False, 'compiled': False, 'compile_only': True,
              'flashable': False, 'hardware_tested': False, 'runtime_abi_compatible': 'NOT_YET_VALIDATED',
              'github': {k: os.environ.get(k, '') for k in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')},
              'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'phase': 'preflight'}
    write(status_path, status)
    try:
        require(1 <= args.jobs <= 4 and args.ram_mb >= 2048, 'Invalid resource budget')
        require(all(not p.exists() and not p.is_symlink() for p in (output, validation_output)), 'Fresh artifact output required')
        c, pc, parent_inputs = check(repo)
        status['source_contract_sha256'] = sha((route / 'power-contract.json').read_bytes())
        status['r79_parent_contract_sha256'] = PARENT_SHA
        parent, multimedia = parent_inputs.parent(repo)
        thermal, thermal_contract = parent.parent(repo)
        inherited = json.loads((repo / thermal_contract['base_contract']).read_text())
        sys.path.insert(0, str(repo / 'r61-build-route'))
        shared = load('r83_shared_build', repo / 'r61-build-route/targeted_battery_build.py')
        resolver = load('r83_output_resolver', repo / 'r78-build-route/resolve_outputs.py')
        old = load('r83_r18', r18 / 'boot_build.py')
        status['r18_bundle_lock_sha256'] = old.verify_bundle()
        helper = load('r83_driver', baseline / 'drivers/driver_check.py')
        runner_data, status['baseline_runner'] = helper.verify_bundle(baseline, package / 'build_platform.py')
        require(sha((package / 'sources.lock.json').read_bytes()) == c['sources_lock_sha256'], 'Source lock changed')
        bazel, options = helper.runner_build_configuration(runner_data, root, args.jobs, args.ram_mb)
        options = list(options) + ['--nokeep_going']
        runner = load('r83_platform', package / 'build_platform.py')
        def logged(command, name):
            runner.logged(command, root, reports / ('r83-' + name + '.log'))
        status['phase'] = 'prepare_frozen_r79_sources'
        write(status_path, status)
        logged([sys.executable, str(package / 'prepare_workspace.py'), '--workspace', str(root)], 'prepare')
        logged([sys.executable, str(baseline / 'run_r12.py'), 'apply', '--workspace', str(root), '--stage', 'soc'], 'r13-apply')
        helper.verify_applied_writes(baseline, root)
        hardware = json.loads((repo / inherited['prerequisite_contract']).read_text())
        for name, sc in [('r60', hardware), ('r61', inherited)]:
            command = [sys.executable, str(repo / sc['integration']['script']), '--workspace', str(root)]
            logged(command, name + '-apply')
            logged(command + ['--check'], name + '-check')
            shared.locked_workspace(root, sc['workspace_files'])
        from apply_thermal import apply as apply_thermal
        from apply_multimedia import apply as apply_multimedia
        from apply_repairs import apply as apply_repairs, verify_applied
        for name, operation, contract in [('thermal', apply_thermal, thermal_contract),
                                          ('multimedia', apply_multimedia, multimedia),
                                          ('repairs', apply_repairs, pc)]:
            write(reports / ('r83-parent-' + name + '-apply.json'), operation(root, repo, contract))
            write(reports / ('r83-parent-' + name + '-check.json'), operation(root, repo, contract, verify=True))
        write(reports / 'r83-parent-postimages.json', verify_applied(root, repo, pc))
        power = load('r83_power_patch', route / 'apply_power.py')
        write(reports / 'r83-power-apply.json', power.apply(root, route))
        write(reports / 'r83-power-check.json', power.apply(root, route, verify=True))
        logged([sys.executable, str(route / 'test_power.py'), '--workspace', str(root),
                '--output', str(reports / 'r83-host-client')], 'source-tests')
        validation = load('r83_validation_build', route / 'validation_only.py')
        write(reports / 'r83-validation-apply.json', validation.prepare(root, route))
        write(reports / 'r83-validation-source-check.json', validation.prepare(root, route, verify=True))
        logged([sys.executable, str(route / 'test_validation.py'), '--workspace', str(root),
                '--output', str(reports / 'r83-host-validation')], 'validation-source-tests')
        runner.build_targets(root, 'soc')  # Metadata only; do not select the aggregate.
        targets = [TARGET] + [m['target'] for m in c['validation_only_modules']] + c['core_targets']
        plan = {'kconfig': bazel + ['build'] + options + ['//vendor/qcom/sm8850:kconfig.msm.generated'],
                'config_validation': bazel + ['build'] + options + ['//vendor/qcom/sm8850:canoe_perf_config'],
                'build': bazel + ['build'] + options + targets,
                'cquery': bazel + ['cquery'] + options + ['--output=files', 'deps(set(' + ' '.join(targets) + '))']}
        write(reports / 'r83-commands.json', plan)
        status.update(phase='analyze_power_target', explicit_build_targets=targets)
        write(status_path, status)
        command = bazel + ['aquery'] + options + ['--output=jsonproto', '--include_artifacts=true',
                   '--include_commandline=true', 'deps(set(' + ' '.join(targets[:-len(c['core_targets'])]) + '))']
        result = subprocess.run(command, cwd=root, text=True, capture_output=True)
        (reports / 'r83-aquery.json').write_text(result.stdout)
        (reports / 'r83-aquery.log').write_text(result.stderr)
        require(result.returncode == 0, 'aquery failed before compilation')
        graph = json.loads(result.stdout)
        selected = [resolver.resolve(graph, c['modules'][0])]
        validation_selected = validation.resolve(graph, c, resolver)
        write(reports / 'r83-transport-build-dependency.json', verify_transport_dependency(graph))
        write(reports / 'r83-actual-target-outputs.json', {'schema': 1, 'runtime_candidates': selected, 'validation_only': validation_selected})
        for row in selected + validation_selected:
            write(reports / ('r83-action-' + row['module_name'] + '.json'),
                  shared.action_chain(graph, row['expected_sources'], row['output']))
        status['phase'] = 'generate_external_kconfig'
        write(status_path, status)
        logged(plan['kconfig'], 'kconfig-build')
        logged(plan['config_validation'], 'external-config-build')
        write(reports / 'r83-effective-adc-config.json', validation.verify_effective_config(root, graph))
        status['phase'] = 'compile_power_and_required_dependencies'
        write(status_path, status)
        logged(plan['build'], 'build')
        result = subprocess.run(plan['cquery'], cwd=root, text=True, capture_output=True)
        (reports / 'r83-cquery.txt').write_text(result.stdout)
        (reports / 'r83-cquery.log').write_text(result.stderr)
        require(result.returncode == 0, 'cquery failed after compilation')
        write(reports / 'r83-all-postbuild-postimages.json', verify_r83_postimages(root, repo, pc, parent_inputs, route))
        write(reports / 'r83-power-postbuild-check.json', power.apply(root, route, verify=True))
        write(reports / 'r83-validation-postbuild-check.json', validation.prepare(root, route, verify=True))
        write(reports / 'r83-effective-adc-config-postbuild.json', validation.verify_effective_config(root, graph))
        status['phase'] = 'collect_source_bound_outputs'
        write(status_path, status)
        status.update(shared.collect_outputs(root, output, c, selected, result.stdout.splitlines(), r18))
        write(reports / 'r83-built-client-metadata.json', verify_built_mca(root, selected[0], output))
        validation_status = shared.collect_outputs(root, validation_output, c, validation_selected, result.stdout.splitlines(), r18)
        write(reports / 'r83-validation-outputs.json', validation.finalize(validation_output, c, validation_selected, validation_status))
        manifest_path = output / 'artifact-manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['source_abi_policy'] = ('Compile-only MCA candidate. Validate its imports, CRCs, namespaces and layout '
                                         'against the exact retained R82 kernel and retained provider modules before selection. '
                                         'Compiled dependency modules and the compiled Image are not replacement candidates.')
        write(manifest_path, manifest)
        status.update(success=True, compiled=True, phase='compiled_source_bound_not_runtime_approved',
                      limitation='Only myron_mca_readonly is a replacement candidate. The retained kernel, QTI transport, R82 CNSS, WLAN and all other modules remain authoritative; exact installed-kernel ABI and device tests are still required. This does not activate full MCA or high-voltage charging control.')
        write(status_path, status)
        shutil.copy2(route / 'power-contract.json', output / 'power-contract.json')
        shutil.copy2(repo / PARENT, output / 'parent-r79-contract.json')
        shutil.copytree(route, output / 'source/r83-build-route', ignore=shutil.ignore_patterns('__pycache__'))
        (output / 'reports').mkdir()
        for report in sorted(reports.glob('r83-*')):
            if report.is_file():
                shutil.copy2(report, output / 'reports' / report.name)
        shutil.copy2(route / 'power-contract.json', validation_output / 'power-contract.json')
        shutil.copytree(route, validation_output / 'source/r83-build-route', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(output / 'reports', validation_output / 'reports')
        for directory in (output, validation_output):
            for folder in ('r83-host-client', 'r83-host-validation'):
                source_report = reports / folder
                if source_report.is_dir():
                    for evidence in source_report.rglob('*'):
                        if evidence.is_file() and evidence.suffix in ('.json', '.log', '.txt'):
                            target = directory / 'reports' / evidence.relative_to(reports)
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(evidence, target)
        write(validation_output / 'artifact-lock.json', {'schema': 1, 'compile_only': True, 'role': 'validation_only', 'activation_allowed': False, 'files': [
            {'file': str(p.relative_to(validation_output)), 'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())}
            for p in sorted(validation_output.rglob('*')) if p.is_file()]})
        write(validation_output / 'validation-complete.json', {'schema': 1, 'compile_only': True, 'flashable': False,
              'role': 'validation_only', 'runtime_candidate_module_names': [], 'activation_allowed': False,
              'required_module_count': len(validation_selected), 'runtime_abi_compatible': 'NOT_YET_VALIDATED',
              'artifact_lock_sha256': sha((validation_output / 'artifact-lock.json').read_bytes()),
              'source_contract_sha256': status['source_contract_sha256']})
        write(output / 'artifact-lock.json', {'schema': 1, 'compile_only': True, 'files': [
            {'file': str(p.relative_to(output)), 'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())}
            for p in sorted(output.rglob('*')) if p.is_file()]})
        write(output / 'candidate-complete.json', {'schema': 1, 'compile_only': True, 'flashable': False,
              'required_module_count': 1, 'runtime_candidate_module_names': [MODULE], 'runtime_abi_compatible': 'NOT_YET_VALIDATED',
              'artifact_lock_sha256': sha((output / 'artifact-lock.json').read_bytes()),
              'source_contract_sha256': status['source_contract_sha256']})
    except Exception as error:
        status.update(success=False, error=str(error))
        print('R83 STOP:', error, file=sys.stderr)
    finally:
        status['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        write(status_path, status)
    return 0 if status['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
