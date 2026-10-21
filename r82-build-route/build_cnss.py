#!/usr/bin/env python3
"""Compile the R82 Myron board firmware selection candidate using the frozen R79 preparation.

Only the CNSS target and its mandatory build dependencies are requested. This
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
TARGET = '//vendor/qcom/sm8850-modules/qcom/opensource/wlan/platform:canoe_perf_cnss2'
MODULE = 'cnss2'
SOURCE_PREFIX = 'vendor/qcom/sm8850-modules/qcom/opensource/wlan/platform/'
HWID_TARGET = '//vendor/qcom/sm8850:canoe_perf/drivers/misc/hwid/hwid'


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
    route = repo / 'r82-build-route'
    c = json.loads((route / 'cnss-contract.json').read_text())
    require(c.get('schema') == 1 and c.get('compile_only') is True and c.get('flashable') is False,
            'Compile-only contract required')
    require(c.get('parent_contract') == PARENT and c.get('parent_contract_sha256') == PARENT_SHA,
            'Wrong parent contract')
    require(sha((repo / PARENT).read_bytes()) == PARENT_SHA, 'Frozen R79 preparation changed')
    pc = json.loads((repo / PARENT).read_text())
    for key in ('baseline_image_sha256', 'baseline_kernel_release', 'sources_lock_sha256', 'git_heads', 'core_targets'):
        require(c.get(key) == pc[key], 'Inherited build preparation changed: ' + key)
    modules = c.get('modules', [])
    require(len(modules) == 1 and modules[0].get('target') == TARGET and modules[0].get('module_name') == MODULE,
            'Unexpected CNSS selection')
    sources = modules[0].get('expected_sources', [])
    require(sources and len(sources) == len(set(sources)) and
            all(s.startswith(SOURCE_PREFIX) and s.endswith('.c') and '..' not in PurePosixPath(s).parts for s in sources),
            'Missing or unsafe patched source bindings')
    source_contract = json.loads((route / 'SOURCE-CONTRACT.json').read_text())
    require(source_contract.get('source_repository') == 'LineageOS/android_kernel_qcom_sm8850-modules' and
            source_contract.get('source_commit') == c['git_heads']['vendor/qcom/sm8850-modules'],
            'CNSS patch source revision differs from locked preparation')
    writes = source_contract.get('writes', [])
    require(writes and {r['path'] for r in writes if r['path'].endswith('.c')} == set(sources),
            'Every patched C file must feed the selected CNSS output')
    require(all(r['path'].startswith(SOURCE_PREFIX) and
                PurePosixPath(r['path']).suffix in ('.c', '.h', '.bzl') and
                '..' not in PurePosixPath(r['path']).parts for r in writes),
            'CNSS auxiliary writes must remain inside the platform source tree')
    rows = c['locked_files']
    names = [row['path'] for row in rows]
    actual = {str(p.relative_to(repo)) for p in route.rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.name != 'cnss-contract.json'}
    require(len(names) == len(set(names)) and set(names) == actual, 'R82 input inventory changed')
    for row in rows:
        relative = PurePosixPath(row['path'])
        require(not relative.is_absolute() and '..' not in relative.parts, 'Unsafe locked path')
        p = repo / relative
        require(not p.is_symlink() and p.resolve().is_relative_to(route.resolve()), 'Redirected locked input')
        data = p.read_bytes()
        require(len(data) == row['bytes'] and sha(data) == row['sha256'], 'Changed locked input: ' + row['path'])
    sys.path.insert(0, str(repo / 'r79-build-route'))
    parent_inputs = load('r82_r79_inputs', repo / 'r79-build-route/r79_inputs.py')
    parent_inputs.check(repo, pc)
    return c, pc, parent_inputs


def verify_hwid_dependency(graph):
    labels = {str(r['id']): r['label'] for r in graph.get('targets', [])}
    require(HWID_TARGET in labels.values(), 'CNSS lacks the actual HWID provider dependency')
    actions = [a for a in graph.get('actions', [])
               if labels.get(str(a.get('targetId'))) == TARGET and
               a.get('mnemonic') == 'KernelModule']
    require(len(actions) == 1, 'Expected one CNSS compile action')
    command = '\n'.join(actions[0].get('arguments', []))
    provider = ('bazel-out/aarch64-fastbuild/bin/vendor/qcom/sm8850/canoe_perf/'
                'drivers/misc/hwid/hwid/canoe_perf/drivers/misc/hwid/hwid_Module.symvers')
    require(provider in command, 'CNSS compile action does not stage HWID Module.symvers')
    makefiles = [a for a in graph.get('actions', [])
                 if labels.get(str(a.get('targetId'))) == TARGET + '_makefiles' and
                 a.get('mnemonic') == 'DdkMakefiles']
    require(len(makefiles) == 1, 'Expected one CNSS DDK makefile action')
    args = makefiles[0].get('arguments', [])
    require('--local-defines' in args, 'CNSS Myron compile switch is absent')
    start = args.index('--local-defines') + 1
    end = next((i for i in range(start, len(args)) if args[i].startswith('--')), len(args))
    defines = args[start:end]
    require(defines.count('MYRON_CNSS_FILE_SELECTION') == 1, 'Wrong Myron CNSS compile switch')
    return {'schema': 1, 'status': 'PASS_HWID_COMPILE_DEPENDENCY',
            'local_defines': defines,
            'consumer_target': TARGET, 'provider_target': HWID_TARGET,
            'staged_provider_symvers': provider,
            'runtime_provider_replacement_allowed': False}


def verify_built_hwid(root, module, output):
    path = root / module['output']
    result = subprocess.run(['readelf', '-sW', str(path)], text=True, capture_output=True)
    require(result.returncode == 0, 'Cannot inspect built CNSS ELF symbol table')
    strong = set()
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) == 8 and fields[4] == 'GLOBAL' and fields[6] == 'UND':
            strong.add(fields[7])
    expected = {'get_hw_version_platform', 'get_hw_country_version'}
    require(expected <= strong, 'Built CNSS lacks one or both actual strong HWID imports')
    inventory = json.loads((output / 'module-inventory.json').read_text())
    require(inventory['module_count'] == 1 and inventory['modules'][0]['name'] == MODULE,
            'CNSS-only KO inventory required')
    require('hwid' in inventory['modules'][0]['depends'], 'Built CNSS does not depend on HWID')
    return {'schema': 1, 'status': 'PASS_BUILT_HWID_IMPORTS',
            'imports': sorted(expected), 'module_dependency': 'hwid',
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
    route = repo / 'r82-build-route'
    reports = root / 'integration-reports'
    output = root / 'integration-artifacts/r82-cnss-candidate'
    status_path = reports / 'r82-status.json'
    status = {'schema': 1, 'success': False, 'compiled': False, 'compile_only': True,
              'flashable': False, 'hardware_tested': False, 'runtime_abi_compatible': 'NOT_YET_VALIDATED',
              'github': {k: os.environ.get(k, '') for k in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')},
              'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'phase': 'preflight'}
    write(status_path, status)
    try:
        require(1 <= args.jobs <= 4 and args.ram_mb >= 2048, 'Invalid resource budget')
        require(not output.exists() and not output.is_symlink(), 'Fresh artifact output required')
        c, pc, parent_inputs = check(repo)
        status['source_contract_sha256'] = sha((route / 'cnss-contract.json').read_bytes())
        status['r79_parent_contract_sha256'] = PARENT_SHA
        parent, multimedia = parent_inputs.parent(repo)
        thermal, thermal_contract = parent.parent(repo)
        inherited = json.loads((repo / thermal_contract['base_contract']).read_text())
        sys.path.insert(0, str(repo / 'r61-build-route'))
        shared = load('r82_shared_build', repo / 'r61-build-route/targeted_battery_build.py')
        resolver = load('r82_output_resolver', repo / 'r78-build-route/resolve_outputs.py')
        old = load('r82_r18', r18 / 'boot_build.py')
        status['r18_bundle_lock_sha256'] = old.verify_bundle()
        helper = load('r82_driver', baseline / 'drivers/driver_check.py')
        runner_data, status['baseline_runner'] = helper.verify_bundle(baseline, package / 'build_platform.py')
        require(sha((package / 'sources.lock.json').read_bytes()) == c['sources_lock_sha256'], 'Source lock changed')
        bazel, options = helper.runner_build_configuration(runner_data, root, args.jobs, args.ram_mb)
        options = list(options) + ['--nokeep_going']
        runner = load('r82_platform', package / 'build_platform.py')
        def logged(command, name):
            runner.logged(command, root, reports / ('r82-' + name + '.log'))
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
            write(reports / ('r82-parent-' + name + '-apply.json'), operation(root, repo, contract))
            write(reports / ('r82-parent-' + name + '-check.json'), operation(root, repo, contract, verify=True))
        write(reports / 'r82-parent-postimages.json', verify_applied(root, repo, pc))
        cnss = load('r82_cnss_patch', route / 'apply_cnss.py')
        write(reports / 'r82-cnss-apply.json', cnss.apply(root, route))
        write(reports / 'r82-cnss-check.json', cnss.apply(root, route, verify=True))
        logged([sys.executable, str(route / 'test_cnss.py'), '--workspace', str(root)], 'source-tests')
        runner.build_targets(root, 'soc')  # Metadata only; do not select the aggregate.
        targets = [TARGET] + c['core_targets']
        plan = {'kconfig': bazel + ['build'] + options + ['//vendor/qcom/sm8850:kconfig.msm.generated'],
                'build': bazel + ['build'] + options + targets,
                'cquery': bazel + ['cquery'] + options + ['--output=files', 'deps(set(' + ' '.join(targets) + '))']}
        write(reports / 'r82-commands.json', plan)
        status.update(phase='analyze_cnss_target', explicit_build_targets=targets)
        write(status_path, status)
        command = bazel + ['aquery'] + options + ['--output=jsonproto', '--include_artifacts=true',
                   '--include_commandline=true', 'deps(' + TARGET + ')']
        result = subprocess.run(command, cwd=root, text=True, capture_output=True)
        (reports / 'r82-aquery.json').write_text(result.stdout)
        (reports / 'r82-aquery.log').write_text(result.stderr)
        require(result.returncode == 0, 'aquery failed before compilation')
        graph = json.loads(result.stdout)
        selected = [resolver.resolve(graph, c['modules'][0])]
        write(reports / 'r82-hwid-build-dependency.json', verify_hwid_dependency(graph))
        write(reports / 'r82-actual-target-outputs.json', {'schema': 1, 'modules': selected})
        for row in selected:
            write(reports / ('r82-action-' + row['module_name'] + '.json'),
                  shared.action_chain(graph, row['expected_sources'], row['output']))
        status['phase'] = 'generate_external_kconfig'
        write(status_path, status)
        logged(plan['kconfig'], 'kconfig-build')
        status['phase'] = 'compile_cnss_and_required_dependencies'
        write(status_path, status)
        logged(plan['build'], 'build')
        result = subprocess.run(plan['cquery'], cwd=root, text=True, capture_output=True)
        (reports / 'r82-cquery.txt').write_text(result.stdout)
        (reports / 'r82-cquery.log').write_text(result.stderr)
        require(result.returncode == 0, 'cquery failed after compilation')
        verify_applied(root, repo, pc)
        write(reports / 'r82-cnss-postbuild-check.json', cnss.apply(root, route, verify=True))
        status['phase'] = 'collect_source_bound_outputs'
        write(status_path, status)
        status.update(shared.collect_outputs(root, output, c, selected, result.stdout.splitlines(), r18))
        write(reports / 'r82-built-hwid-imports.json', verify_built_hwid(root, selected[0], output))
        manifest_path = output / 'artifact-manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['source_abi_policy'] = ('Compile-only CNSS candidate. Validate its imports, CRCs, namespaces and layout '
                                         'against the exact running R79 kernel and retained provider modules before selection. '
                                         'Compiled dependency modules and the compiled Image are not replacement candidates.')
        write(manifest_path, manifest)
        status.update(success=True, compiled=True, phase='compiled_source_bound_not_runtime_approved',
                      limitation='Only cnss2 is a replacement candidate. The retained kernel, hwid, R81 WLAN and other modules remain authoritative; exact installed-kernel and consumer ABI plus device tests are still required.')
        write(status_path, status)
        shutil.copy2(route / 'cnss-contract.json', output / 'cnss-contract.json')
        shutil.copy2(repo / PARENT, output / 'parent-r79-contract.json')
        shutil.copytree(route, output / 'source/r82-build-route', ignore=shutil.ignore_patterns('__pycache__'))
        (output / 'reports').mkdir()
        for report in sorted(reports.glob('r82-*')):
            if report.is_file():
                shutil.copy2(report, output / 'reports' / report.name)
        write(output / 'artifact-lock.json', {'schema': 1, 'compile_only': True, 'files': [
            {'file': str(p.relative_to(output)), 'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())}
            for p in sorted(output.rglob('*')) if p.is_file()]})
        write(output / 'candidate-complete.json', {'schema': 1, 'compile_only': True, 'flashable': False,
              'required_module_count': 1, 'runtime_abi_compatible': 'NOT_YET_VALIDATED',
              'artifact_lock_sha256': sha((output / 'artifact-lock.json').read_bytes()),
              'source_contract_sha256': status['source_contract_sha256']})
    except Exception as error:
        status.update(success=False, error=str(error))
        print('R82 STOP:', error, file=sys.stderr)
    finally:
        status['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        write(status_path, status)
    return 0 if status['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
