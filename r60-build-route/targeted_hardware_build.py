#!/usr/bin/env python3
"""Explicit camera and rmnet_perf DDK build using the proven R55 preparation route.

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
from check_hardware_inputs import check

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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'package', 'baseline', 'r18', 'repo-root', 'contract'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--ram-mb', type=int, default=10000)
    args = parser.parse_args()
    root, package, baseline, r18, repo = [getattr(args, n).resolve() for n in ('workspace', 'package', 'baseline', 'r18', 'repo_root')]
    reports = root / 'integration-reports'
    output = root / 'integration-artifacts/r60-targeted-hardware'
    status_path = reports / 'r60-targeted-status.json'
    status = {'schema': 1, 'success': False, 'compiled': False, 'flashable': False, 'hardware_tested': False,
              'github': {key: os.environ.get(key, '') for key in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')},
              'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'phase': 'preflight'}
    output_owned = False
    write(status_path, status)
    try:
        require(not output.is_symlink(), 'Redirected artifact output')
        if output.exists():
            shutil.rmtree(output)
        contract = json.loads(args.contract.read_text())
        check(repo, contract)
        require(1 <= args.jobs <= 8 and args.ram_mb >= 2048, 'Invalid resources')
        old = load('r60_r18', r18 / 'boot_build.py')
        status['r18_bundle_lock_sha256'] = old.verify_bundle()
        helper = load('r60_driver', baseline / 'drivers/driver_check.py')
        runner_data, status['baseline_runner'] = helper.verify_bundle(baseline, package / 'build_platform.py')
        bazel, options = helper.runner_build_configuration(runner_data, root, args.jobs, args.ram_mb)
        runner = load('r60_platform', package / 'build_platform.py')
        runner.logged([sys.executable, str(package / 'prepare_workspace.py'), '--workspace', str(root)], root, reports / 'r60-targeted-prepare.log')
        runner.logged([sys.executable, str(baseline / 'run_r12.py'), 'apply', '--workspace', str(root), '--stage', 'soc'], root, reports / 'r60-targeted-r13-apply.log')
        helper.verify_applied_writes(baseline, root)
        integration = repo / contract['integration']['script']
        command = [sys.executable, str(integration), '--workspace', str(root)]
        runner.logged(command, root, reports / 'r60-targeted-hardware-apply.log')
        runner.logged(command + ['--check'], root, reports / 'r60-targeted-hardware-check.log')
        locked_workspace(root, contract['workspace_files'])
        runner.build_targets(root, 'soc')  # Emit release filegroup, ignore aggregate labels.
        modules = contract['modules']
        targets = [row['target'] for row in modules] + ['//common:kernel_aarch64', '//myron_artifact_metadata:kernel_release']
        require(len(targets) == len(set(targets)), 'Duplicate build targets')
        status.update(phase='analyze_explicit_targets', explicit_build_targets=targets)
        write(status_path, status)
        plan = {'build': bazel + ['build'] + options + targets,
                'cquery': bazel + ['cquery'] + options + ['--output=files', 'deps(set(' + ' '.join(targets) + '))']}
        write(reports / 'r60-targeted-commands.json', plan)
        # Analyze the actual source-to-output chain before the expensive core build.
        for index, row in enumerate(modules):
            command = bazel + ['aquery'] + options + ['--output=jsonproto', '--include_artifacts=true',
                         '--include_commandline=true', 'deps(' + row['target'] + ')']
            result = subprocess.run(command, cwd=root, text=True, capture_output=True)
            (reports / f'r60-targeted-aquery-{index}.json').write_text(result.stdout)
            (reports / f'r60-targeted-aquery-{index}.log').write_text(result.stderr)
            require(result.returncode == 0, 'aquery analysis failed before build')
            write(reports / f'r60-targeted-action-{index}.json', action_chain(json.loads(result.stdout), row['expected_sources'], row['output']))
        status['phase'] = 'compile_explicit_hardware_targets'
        write(status_path, status)
        runner.logged(plan['build'], root, reports / 'r60-targeted-build.log')
        status.update(compiled=True, phase='collect_outputs')
        result = subprocess.run(plan['cquery'], cwd=root, text=True, capture_output=True)
        (reports / 'r60-targeted-cquery.txt').write_text(result.stdout)
        (reports / 'r60-targeted-cquery.log').write_text(result.stderr)
        require(result.returncode == 0, 'cquery failed')
        locked_workspace(root, contract['workspace_files'])
        required = {row['output'] for row in modules} | {CORE + name for name in CORE_REQUIRED}
        required.update(row['symvers'] for row in modules)
        records = []
        output.mkdir(parents=True)
        output_owned = True
        for name in dict.fromkeys(result.stdout.splitlines()):
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
        write(output / 'artifact-manifest.json', {'schema': 1, 'files': records, 'missing': sorted(missing), 'flashable': False})
        require(not missing, 'Required compiler output missing')
        status['built_image_sha256'] = sha((output / 'objects' / CORE / 'Image').read_bytes())
        status['built_image_matches_runtime_baseline'] = status['built_image_sha256'] == contract['baseline_image_sha256']
        release = (output / 'objects' / CORE / 'include/config/kernel.release').read_text().strip()
        require(release == contract['baseline_kernel_release'], 'Unexpected kernel release')
        sys.path.insert(0, str(r18 / 'stage-builder'))
        from elf_contract import parse_elf
        identities = []
        for row in modules:
            data = (output / 'objects' / row['output']).read_bytes()
            elf = parse_elf(data)
            require(elf['name'] == row['module_name'], 'Wrong compiled module name')
            require(elf['info']['vermagic'][0].split()[0] == release, 'Wrong module release')
            identities.append({'name': elf['name'], 'sha256': sha(data), 'vermagic': elf['info']['vermagic'][0]})
        write(output / 'module-identity.json', {'modules': identities, 'runtime_abi_compatible': 'NOT_YET_VALIDATED'})
        status.update(success=True, phase='compiled_and_source_bound', limitation='Actual installed-kernel import CRC/namespace/signature checks and device tests remain mandatory.')
    except Exception as error:
        status['error'] = str(error)
        print('R60 STOP:', error, file=sys.stderr)
    finally:
        status['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        write(status_path, status)
        if output_owned and output.is_dir() and not output.is_symlink():
            dest = output / 'reports'
            dest.mkdir(exist_ok=True)
            for p in reports.glob('r60-targeted-*'):
                if p.is_file():
                    shutil.copy2(p, dest / p.name)
            shutil.copy2(args.contract, output / 'hardware-contract.json')
            write(output / 'artifact-lock.json', {'schema': 1, 'success': status['success'], 'files': [
                {'file': str(p.relative_to(output)), 'sha256': sha(p.read_bytes()), 'bytes': p.stat().st_size}
                for p in sorted(output.rglob('*')) if p.is_file() and p.name != 'artifact-lock.json']})
    return 0 if status['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
