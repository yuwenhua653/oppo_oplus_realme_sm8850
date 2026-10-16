#!/usr/bin/env python3
"""Compile-only MCA service DDK build using the proven R55 preparation route.

Refuses any incomplete source review or unexpected source hashes.
No boot image is generated. No modules from the baseline are replaced here.
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

from action_chain import action_chain
from check_battery_inputs import check

CORE = 'bazel-out/aarch64-fastbuild/bin/common/kernel_aarch64/'
CORE_REQUIRED = {'Image', 'vmlinux.symvers', 'kernel_aarch64_dot_config',
                 'include/config/kernel.release', 'modules.builtin', 'modules.builtin.modinfo'}


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


def locked_workspace(root, rows):
    require(rows, 'Missing expected integrated source hashes')
    for row in rows:
        p = PurePosixPath(row['path'])
        require(not p.is_absolute() and '..' not in p.parts, 'Unsafe integrated path')
        local = root / p
        require(local.is_file() and not local.is_symlink(), 'Missing/redirected integrated source')
        require(local.resolve().is_relative_to(root), 'Integrated source escapes workspace')
        require(sha(local.read_bytes()) == row['sha256'], 'Integrated source mismatch: ' + str(p))


def declared_outputs(graph):
    """Catch wrong predicted symvers/KO names during analysis, before compilation."""
    fragments = {str(r['id']): r for r in graph.get('pathFragments', [])}
    cache = {}

    def path(key, seen=None):
        key = str(key)
        if key in cache:
            return cache[key]
        seen = set() if seen is None else seen
        require(key in fragments and key not in seen, 'Invalid graph path fragment')
        seen.add(key)
        row = fragments[key]
        parent = str(row.get('parentId', '0'))
        value = (path(parent, seen) + '/' if parent not in ('0', '') else '') + row['label']
        seen.remove(key)
        cache[key] = value
        return value

    artifacts = {str(r['id']): r.get('execPath') or path(r['pathFragmentId'])
                 for r in graph.get('artifacts', [])}
    return {artifacts[str(i)] for a in graph.get('actions', []) for i in a.get('outputIds', [])}


def collect_outputs(root, output, contract, modules, candidates, r18, generated_files=(), diagnostic=False, auxiliary=(), closure=()):
    """Share output checks; only a fully checked subset gets an upload manifest."""
    # The generated private header must remain exact bytes from the pinned core.
    generated_reviews = []
    for row in generated_files:
        original, generated = root / row['source'], root / row['output']
        require(original.read_bytes() == generated.read_bytes(), 'Generated header differs from pinned source')
        generated_reviews.append({'source': row['source'], 'output': row['output'],
                                  'sha256': sha(original.read_bytes())})
    if not diagnostic:
        write(root / 'integration-reports/r61-targeted-generated-inputs.json', generated_reviews)
    require(not diagnostic or not closure, 'Diagnostic subset must not include the full runtime closure')
    selected = list(modules) + list(auxiliary) + list(closure)
    expected_names = sorted(row['module_name'] for row in selected)
    require(len(expected_names) == len({name.replace('-', '_') for name in expected_names}),
            'Duplicate normalized compiled module name')
    required = {row['output'] for row in selected} | {CORE + name for name in CORE_REQUIRED}
    required.update(row['symvers'] for row in selected)
    required.update(row['output'] for row in generated_files)
    records = []
    output.mkdir(parents=True)
    collected_candidates = candidates + [row['output'] for row in generated_files]
    for name in dict.fromkeys(collected_candidates):
        if name not in required and not (name.startswith('bazel-out/aarch64-fastbuild/bin/') and name.endswith('.symvers')):
            continue
        p = PurePosixPath(name)
        require(not p.is_absolute() and '..' not in p.parts and name.startswith('bazel-out/'), 'Unsafe output')
        data = (root / p).read_bytes()
        target = output / 'objects' / p
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        records.append({'file': 'objects/' + name, 'source': name, 'bytes': len(data), 'sha256': sha(data)})
    missing = required - {row['source'] for row in records}
    manifest = {'schema': 1, 'files': records, 'missing': sorted(missing), 'flashable': False,
                'auxiliary_provider_names': [row['module_name'] for row in auxiliary],
                'runtime_closure_module_names': [row['module_name'] for row in closure],
                'source_abi_policy': 'Compile only. Source ABI providers must not be mixed with old CP/buck/FG modules.'}
    if not diagnostic:
        write(output / 'artifact-manifest.json', manifest)
    require(not missing, 'Required compiler output missing')
    built_image_sha256 = sha((output / 'objects' / CORE / 'Image').read_bytes())
    built_image_matches_runtime_baseline = built_image_sha256 == contract['baseline_image_sha256']
    release = (output / 'objects' / CORE / 'include/config/kernel.release').read_text().strip()
    require(release == contract['baseline_kernel_release'], 'Unexpected kernel release')
    sys.path.insert(0, str(r18 / 'stage-builder'))
    from elf_contract import parse_elf
    identities = []
    inventory = []
    for row in selected:
        data = (output / 'objects' / row['output']).read_bytes()
        elf = parse_elf(data)
        require(elf['name'] == row['module_name'], 'Wrong compiled module name')
        require(elf['info']['vermagic'][0].split()[0] == release, 'Wrong module release')
        identities.append({'name': elf['name'], 'sha256': sha(data), 'vermagic': elf['info']['vermagic'][0]})
        inventory.append({'name': elf['name'], 'file': 'objects/' + row['output'],
                          'bytes': len(data), 'sha256': sha(data),
                          'depends': [name for value in elf['info'].get('depends', [])
                                      for name in value.split(',') if name]})
    actual_ko_files = {str(path.relative_to(output)) for path in output.rglob('*.ko') if path.is_file()}
    require(actual_ko_files == {row['file'] for row in inventory}, 'Actual KO file inventory differs from required compiler outputs')
    require(sorted(row['name'] for row in inventory) == expected_names, 'Actual ELF module inventory differs from required module names')
    write(output / 'module-inventory.json', {'schema': 1, 'compile_only': True, 'flashable': False,
        'compiled_collection_complete': True, 'required_module_names': expected_names,
        'module_count': len(inventory), 'modules': inventory,
        'runtime_abi_compatible': 'NOT_YET_VALIDATED',
        'scope': 'Every explicitly reviewed KO is materialized and ELF-identified. Dependency names, source API and installed-kernel ABI still require a separate runtime assembly review.'})
    write(output / 'module-identity.json', {
        'modules': [row for row in identities if row['name'] in {m['module_name'] for m in modules}],
        'auxiliary_providers': [row for row in identities if row['name'] in {m['module_name'] for m in auxiliary}],
        'runtime_closure_modules': [row for row in identities if row['name'] in {m['module_name'] for m in closure}],
        'runtime_abi_compatible': 'NOT_YET_VALIDATED'})
    if diagnostic:
        manifest.update(scope='diagnostic_subset', partial=True, selected_module_names=[row['module_name'] for row in modules],
                        full_module_count=len(contract['modules']), compiled=True, compile_only=True,
                        validated_subset=True, full_build_not_passed=True, hardware_tested=False,
                        built_image_sha256=built_image_sha256,
                        built_image_matches_runtime_baseline=built_image_matches_runtime_baseline,
                        runtime_abi_compatible='NOT_YET_VALIDATED')
        write(output / 'diagnostic-manifest.json', manifest)
    return {'built_image_sha256': built_image_sha256,
            'built_image_matches_runtime_baseline': built_image_matches_runtime_baseline}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'package', 'baseline', 'r18', 'repo-root', 'contract'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--ram-mb', type=int, default=10000)
    args = parser.parse_args()
    require(args.contract.is_file(), 'Missing source contract')
    root, package, baseline, r18, repo = [getattr(args, n).resolve() for n in ('workspace', 'package', 'baseline', 'r18', 'repo_root')]
    reports = root / 'integration-reports'
    output = root / 'integration-artifacts/r61-targeted-battery'
    diagnostic_output = output.with_name('r61-targeted-diagnostic')
    status_path = reports / 'r61-targeted-status.json'
    status = {'schema': 1, 'success': False, 'compiled': False, 'compile_only': True, 'flashable': False, 'hardware_tested': False,
              'github': {key: os.environ.get(key, '') for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')},
              'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'phase': 'preflight'}
    output_owned = False
    write(status_path, status)
    try:
        for directory in (output, diagnostic_output):
            require(not directory.is_symlink(), 'Redirected artifact output')
            if directory.exists():
                shutil.rmtree(directory)
        contract = json.loads(args.contract.read_text())
        check(repo, contract)
        prior_contract_path = repo / contract['prerequisite_contract']
        prior_contract = json.loads(prior_contract_path.read_text())
        prior_checker = load('r61_prior_check', prior_contract_path.parent / 'check_hardware_inputs.py')
        prior_checker.check(repo, prior_contract)
        status['source_contract_sha256'] = sha(args.contract.read_bytes())
        status['prerequisite_contract_sha256'] = sha(prior_contract_path.read_bytes())
        status['candidate_module_names'] = [row['module_name'] for row in contract['modules']]
        status['candidate_module_count'] = len(contract['modules'])
        status['auxiliary_provider_names'] = [row['module_name'] for row in contract.get('auxiliary_providers', [])]
        status['runtime_closure_module_names'] = [row['module_name'] for row in contract.get('runtime_closure_modules', [])]
        status['integration_sequence'] = ['unchanged_R13_apply_and_verify', 'unchanged_R60_apply_and_check', 'R61_apply_and_check']
        require(1 <= args.jobs <= 8 and args.ram_mb >= 2048, 'Invalid resources')
        old = load('r61_r18', r18 / 'boot_build.py')
        status['r18_bundle_lock_sha256'] = old.verify_bundle()
        helper = load('r61_driver', baseline / 'drivers/driver_check.py')
        runner_data, status['baseline_runner'] = helper.verify_bundle(baseline, package / 'build_platform.py')
        bazel, options = helper.runner_build_configuration(runner_data, root, args.jobs, args.ram_mb)
        runner = load('r61_platform', package / 'build_platform.py')
        runner.logged([sys.executable, str(package / 'prepare_workspace.py'), '--workspace', str(root)], root, reports / 'r61-targeted-prepare.log')
        runner.logged([sys.executable, str(baseline / 'run_r12.py'), 'apply', '--workspace', str(root), '--stage', 'soc'], root, reports / 'r61-targeted-r13-apply.log')
        helper.verify_applied_writes(baseline, root)
        prior_command = [sys.executable, str(repo / prior_contract['integration']['script']), '--workspace', str(root)]
        runner.logged(prior_command, root, reports / 'r61-targeted-r60-apply.log')
        runner.logged(prior_command + ['--check'], root, reports / 'r61-targeted-r60-check.log')
        locked_workspace(root, prior_contract['workspace_files'])
        integration = repo / contract['integration']['script']
        command = [sys.executable, str(integration), '--workspace', str(root)]
        runner.logged(command, root, reports / 'r61-targeted-battery-apply.log')
        runner.logged(command + ['--check'], root, reports / 'r61-targeted-battery-check.log')
        locked_workspace(root, contract['workspace_files'])
        runner.build_targets(root, 'soc')  # Emit release filegroup, ignore aggregate labels.
        modules = contract['modules']
        auxiliary = contract.get('auxiliary_providers', [])
        closure = contract.get('runtime_closure_modules', [])
        selected = modules + auxiliary + closure
        diagnostic_auxiliary = [row for row in auxiliary if row['module_name'] in contract.get('diagnostic_auxiliary_providers', [])]
        # A dependency may build only Module.symvers/staging, leaving its final
        # KO CopyOutputs action unexecuted. Explicitly request every KO we collect.
        targets = [row['target'] for row in selected] + ['//common:kernel_aarch64', '//myron_artifact_metadata:kernel_release']
        require(len(targets) == len(set(targets)), 'Duplicate build targets')
        status.update(phase='analyze_explicit_targets', explicit_build_targets=targets)
        write(status_path, status)
        plan = {'build': bazel + ['build'] + options + targets,
                'cquery': bazel + ['cquery'] + options + ['--output=files', 'deps(set(' + ' '.join(targets) + '))']}
        write(reports / 'r61-targeted-commands.json', plan)
        # Analyze the actual source-to-output chain before the expensive core build.
        command = bazel + ['aquery'] + options + ['--output=jsonproto', '--include_artifacts=true',
                     '--include_commandline=true', 'deps(set(' + ' '.join(row['target'] for row in selected) + '))']
        result = subprocess.run(command, cwd=root, text=True, capture_output=True)
        (reports / 'r61-targeted-aquery.json').write_text(result.stdout)
        (reports / 'r61-targeted-aquery.log').write_text(result.stderr)
        require(result.returncode == 0, 'aquery analysis failed before build')
        graph = json.loads(result.stdout)
        required_analysis_outputs = {row[key] for row in selected for key in ('output', 'symvers')}
        required_analysis_outputs.update(row['output'] for row in contract.get('generated_files', []))
        missing_analysis_outputs = required_analysis_outputs - declared_outputs(graph)
        require(not missing_analysis_outputs, 'Expected KO/symvers not declared before compile: ' + str(sorted(missing_analysis_outputs)))
        for index, row in enumerate(selected):
            required_inputs = row['expected_sources'] + row.get('generated_inputs', [])
            write(reports / f'r61-targeted-action-{index}.json', action_chain(graph, required_inputs, row['output']))
        # Preserve every reviewed diagnostic KO before unrelated MCA targets can fail.
        diagnostic_names = contract.get('diagnostic_module_names', ['bq27z561', 'camera'])
        diagnostic_modules = [row for row in modules if row['module_name'] in diagnostic_names]
        require(sorted(row['module_name'] for row in diagnostic_modules) == sorted(diagnostic_names),
                'Diagnostic subset differs from reviewed module scope')
        diagnostic_targets = [row['target'] for row in diagnostic_modules + diagnostic_auxiliary] + targets[-2:]
        diagnostic_plan = {'build': bazel + ['build'] + options + diagnostic_targets,
                           'cquery': bazel + ['cquery'] + options + ['--output=files', 'deps(set(' + ' '.join(diagnostic_targets) + '))']}
        write(reports / 'r61-targeted-diagnostic-commands.json', diagnostic_plan)
        status['phase'] = 'compile_diagnostic_subset'
        write(status_path, status)
        runner.logged(diagnostic_plan['build'], root, reports / 'r61-targeted-diagnostic-build.log')
        result = subprocess.run(diagnostic_plan['cquery'], cwd=root, text=True, capture_output=True)
        (reports / 'r61-targeted-diagnostic-cquery.txt').write_text(result.stdout)
        (reports / 'r61-targeted-diagnostic-cquery.log').write_text(result.stderr)
        require(result.returncode == 0, 'Diagnostic cquery failed')
        locked_workspace(root, contract['workspace_files'])
        status['phase'] = 'collect_diagnostic_outputs'
        write(status_path, status)
        collect_outputs(root, diagnostic_output, contract, diagnostic_modules, result.stdout.splitlines(), r18, diagnostic=True, auxiliary=diagnostic_auxiliary)
        status['diagnostic_subset_verified'] = True
        status['phase'] = 'compile_explicit_battery_targets'
        write(status_path, status)
        runner.logged(plan['build'], root, reports / 'r61-targeted-build.log')
        status.update(compiled=True, phase='collect_outputs')
        result = subprocess.run(plan['cquery'], cwd=root, text=True, capture_output=True)
        (reports / 'r61-targeted-cquery.txt').write_text(result.stdout)
        (reports / 'r61-targeted-cquery.log').write_text(result.stderr)
        require(result.returncode == 0, 'cquery failed')
        locked_workspace(root, contract['workspace_files'])
        output_owned = True
        status.update(collect_outputs(root, output, contract, modules, result.stdout.splitlines(), r18,
                                      contract.get('generated_files', []), auxiliary=auxiliary, closure=closure))
        status.update(success=True, phase='compiled_and_source_bound', limitation='Actual installed-kernel import CRC/namespace/signature checks and device tests remain mandatory.')
    except Exception as error:
        status['error'] = str(error)
        print('R61 STOP:', error, file=sys.stderr)
    finally:
        status['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        write(status_path, status)
        for directory, diagnostic in ((output, False), (diagnostic_output, True)):
            owned = status.get('diagnostic_subset_verified', False) if diagnostic else output_owned
            if not owned or not directory.is_dir() or directory.is_symlink():
                continue
            if diagnostic:
                manifest_path = directory / 'diagnostic-manifest.json'
                manifest = json.loads(manifest_path.read_text())
                manifest.update(full_build_not_passed=not status['success'], source_contract_sha256=status['source_contract_sha256'])
                write(manifest_path, manifest)
            dest = directory / 'reports'
            dest.mkdir(exist_ok=True)
            for p in reports.glob('r61-targeted-*'):
                if p.is_file():
                    shutil.copy2(p, dest / p.name)
            shutil.copy2(args.contract, directory / 'battery-contract.json')
            write(directory / 'artifact-lock.json', {'schema': 1, 'success': status['success'],
                'scope': 'diagnostic_subset' if diagnostic else 'full_candidates', 'compile_only': True,
                'full_build_not_passed': not status['success'], 'files': [
                {'file': str(p.relative_to(directory)), 'sha256': sha(p.read_bytes()), 'bytes': p.stat().st_size}
                for p in sorted(directory.rglob('*')) if p.is_file() and p.name != 'artifact-lock.json']})
            if diagnostic:
                marker = directory / 'diagnostic-complete.json'
                write(marker.with_suffix('.tmp'), {'scope': 'diagnostic_subset', 'compile_only': True,
                    'full_build_not_passed': not status['success'], 'runtime_abi_compatible': 'NOT_YET_VALIDATED',
                    'artifact_lock_sha256': sha((directory / 'artifact-lock.json').read_bytes()),
                    'diagnostic_manifest_sha256': sha((directory / 'diagnostic-manifest.json').read_bytes())})
                marker.with_suffix('.tmp').replace(marker)
            elif status['success']:
                marker = directory / 'candidate-complete.json'
                write(marker.with_suffix('.tmp'), {'scope': 'full_candidates', 'compile_only': True,
                    'runtime_abi_compatible': 'NOT_YET_VALIDATED',
                    'artifact_lock_sha256': sha((directory / 'artifact-lock.json').read_bytes()),
                    'module_inventory_sha256': sha((directory / 'module-inventory.json').read_bytes()),
                    'required_module_count': len(contract['modules']) + len(contract.get('auxiliary_providers', [])) + len(contract.get('runtime_closure_modules', []))})
                marker.with_suffix('.tmp').replace(marker)
    return 0 if status['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
