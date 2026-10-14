#!/usr/bin/env python3
"""Compile one R55 PAS target and core metadata using the pinned R18/R13 setup.

The cold core-kernel build and declared Bazel prerequisites are unavoidable.
This driver never invokes the 142-module boot stage or the full-device stage.
All outputs are diagnostic source-build evidence, never partition images.
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

HERE = Path(__file__).resolve().parent
PATCH = HERE.parent / 'dsp-auto-boot'
PAS_TARGET = '//vendor/qcom/sm8850:canoe_perf/drivers/remoteproc/qcom_q6v5_pas'
TARGETS = [PAS_TARGET, '//common:kernel_aarch64', '//myron_artifact_metadata:kernel_release']
PAS_OUTPUT = 'bazel-out/aarch64-fastbuild/bin/vendor/qcom/sm8850/canoe_perf/drivers/remoteproc/qcom_q6v5_pas/qcom_q6v5_pas.ko'
PAS_SYMVERS = 'bazel-out/aarch64-fastbuild/bin/vendor/qcom/sm8850/canoe_perf/drivers/remoteproc/qcom_q6v5_pas/canoe_perf/drivers/remoteproc/qcom_q6v5_pas_Module.symvers'
CORE = 'bazel-out/aarch64-fastbuild/bin/common/kernel_aarch64/'
SOURCE = 'vendor/qcom/sm8850/drivers/remoteproc/qcom_q6v5_pas.c'
CORE_REQUIRED = {'Image', 'vmlinux.symvers', 'kernel_aarch64_dot_config',
                 'include/config/kernel.release', 'modules.builtin', 'modules.builtin.modinfo'}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def safe_output(name):
    path = PurePosixPath(name)
    require(not path.is_absolute() and '..' not in path.parts and name.startswith('bazel-out/'), 'Unsafe cquery path: ' + name)
    return path


def commands(bazel, options):
    """Build only explicit three targets; query their declared graph afterward."""
    roots = 'set(' + ' '.join(TARGETS) + ')'
    return {
        'build': bazel + ['build'] + options + TARGETS,
        'cquery': bazel + ['cquery'] + options + ['--output=files', 'deps(' + roots + ')'],
        'aquery': bazel + ['aquery'] + options + ['--output=jsonproto', '--include_artifacts=true',
                   '--include_commandline=true', 'outputs(".*qcom_q6v5_pas.*", deps(' + PAS_TARGET + '))'],
    }


def action_evidence(document):
    """Locate PAS source in the actual action that emits the requested .ko."""
    fragments = {str(row['id']): row for row in document.get('pathFragments', [])}
    cache = {}

    def fragment(identifier, visiting=None):
        identifier = str(identifier)
        if identifier in cache:
            return cache[identifier]
        visiting = set() if visiting is None else visiting
        require(identifier not in visiting and identifier in fragments, 'Invalid aquery path fragment')
        visiting.add(identifier)
        row = fragments[identifier]
        parent = str(row.get('parentId', '0'))
        result = (fragment(parent, visiting) + '/' if parent not in ('0', '') else '') + row['label']
        visiting.remove(identifier)
        cache[identifier] = result
        return result

    artifacts = {str(row['id']): row.get('execPath') or fragment(row['pathFragmentId'])
                 for row in document.get('artifacts', [])}
    depsets = {str(row['id']): row for row in document.get('depSetOfFiles', [])}
    input_cache = {}

    def inputs(identifier, visiting=None):
        identifier = str(identifier)
        if identifier in input_cache:
            return input_cache[identifier]
        visiting = set() if visiting is None else visiting
        require(identifier in depsets and identifier not in visiting, 'Invalid aquery input depset')
        visiting.add(identifier)
        row = depsets[identifier]
        result = {artifacts[str(value)] for value in row.get('directArtifactIds', [])}
        for child in row.get('transitiveDepSetIds', []):
            result.update(inputs(child, visiting))
        visiting.remove(identifier)
        input_cache[identifier] = result
        return result

    candidates = []
    for action in document.get('actions', []):
        outputs = [artifacts[str(value)] for value in action.get('outputIds', [])]
        if PAS_OUTPUT not in outputs:
            continue
        files = set()
        for identifier in action.get('inputDepSetIds', []):
            files.update(inputs(identifier))
        if SOURCE in files:
            candidates.append({'mnemonic': action.get('mnemonic'), 'action_key': action.get('actionKey'),
                               'source': SOURCE, 'source_is_declared_input': True,
                               'output': PAS_OUTPUT, 'declared_input_count': len(files),
                               'arguments': action.get('arguments', [])})
    require(len(candidates) == 1, 'Expected exactly one PAS-producing action with the patched C source as input')
    return candidates[0]


def collect(root, names, destination, elf_parser):
    require(not destination.exists(), 'Refusing stale artifact directory')
    destination.mkdir(parents=True)
    records, present = [], set()
    for name in dict.fromkeys(names):
        retain = name == PAS_OUTPUT or name in {CORE + value for value in CORE_REQUIRED}
        retain |= name.endswith('.symvers') and name.startswith('bazel-out/aarch64-fastbuild/bin/')
        if not retain:
            continue
        # deps() also enumerates source and external-repository files. They are
        # graph evidence, not compiled outputs; only validate/copy our allowlist.
        path = safe_output(name)
        source = root / path
        require(source.is_file(), 'Declared fresh output missing: ' + name)
        data = source.read_bytes()
        target = destination / 'objects' / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        require(target.read_bytes() == data, 'Artifact readback mismatch')
        records.append({'file': 'objects/' + name, 'source': name, 'bytes': len(data), 'sha256': sha(data)})
        present.add(name)
    missing = sorted(({CORE + value for value in CORE_REQUIRED} | {PAS_OUTPUT, PAS_SYMVERS}) - present)
    manifest = {'schema': 1, 'stage': 'r55-targeted-pas', 'files': records,
                'missing_required_outputs': missing, 'flashable': False, 'hardware_tested': False,
                'scope': 'One freshly compiled PAS module plus core-kernel ABI/provenance outputs; no runtime module selection.'}
    write_json(destination / 'artifact-manifest.json', manifest)
    require(not missing, 'Missing compiled outputs: ' + ', '.join(missing))
    core = destination / 'objects' / CORE
    image = (core / 'Image').read_bytes()
    release = (core / 'include/config/kernel.release').read_text().strip()
    config = (core / 'kernel_aarch64_dot_config').read_text()
    require(image[56:60] == b'ARMd', 'Expected raw AArch64 Image')
    require(release and b'Linux version ' + release.encode() + b' ' in image, 'Image/kernel.release mismatch')
    require('CONFIG_ARM64_4K_PAGES=y\n' in config, 'Unexpected kernel page size')
    module = destination / 'objects' / PAS_OUTPUT
    elf = elf_parser(module.read_bytes())
    require(elf['name'] == 'qcom_q6v5_pas', 'Wrong compiled module identity')
    require(elf['info']['vermagic'][0].split()[0] == release, 'PAS/core release mismatch')
    write_json(destination / 'module-identity.json', {'name': elf['name'], 'vermagic': elf['info']['vermagic'][0],
               'bytes': module.stat().st_size, 'sha256': sha(module.read_bytes()), 'kernel_release': release,
               'runtime_abi_compatible': 'NOT_YET_VALIDATED', 'hardware_tested': False})
    (destination / 'NOT-A-FLASH-PACKAGE.txt').write_text(
        'R55 PAS 源码编译诊断产物，不含分区镜像。新 Image 仅用于构建证据；必须审核新模块与现有内核 ABI 后才能装配测试包。\n')
    return module


def run(args):
    root, package, baseline, r18 = [getattr(args, name).resolve() for name in ('workspace', 'package', 'baseline', 'r18')]
    reports = root / 'integration-reports'
    reports.mkdir(parents=True, exist_ok=True)
    output = root / 'integration-artifacts/r55-targeted-pas'
    status_path = reports / 'r55-targeted-status.json'
    status = {'schema': 1, 'success': False, 'compiled': False, 'flashable': False, 'hardware_tested': False,
              'phase': 'verify_inputs', 'explicit_build_targets': TARGETS,
              'github': {name: os.environ.get(name, '') for name in ('GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')},
              'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    output_owned = False
    # Publish failure by default before any cleanup can fail.
    write_json(status_path, status)
    try:
        # Remove only this driver's previous outputs. Never follow a symlink or
        # let an early cleanup error leave a previous successful status behind.
        require(not output.is_symlink(), 'Refuse redirected artifact directory')
        if output.exists():
            shutil.rmtree(output)
        for path in reports.glob('r55-targeted-*'):
            if path != status_path and path.is_file():
                path.unlink()
        require(1 <= args.jobs <= 8 and args.ram_mb >= 2048, 'Invalid build resources')
        old = load('r55_locked_r18', r18 / 'boot_build.py')
        status['r18_bundle_lock_sha256'] = old.verify_bundle()
        helper = load('r55_driver_check', baseline / 'drivers/driver_check.py')
        runner_data, status['baseline_runner'] = helper.verify_bundle(baseline, package / 'build_platform.py')
        bazel, options = helper.runner_build_configuration(runner_data, root, args.jobs, args.ram_mb)
        runner = load('r55_locked_platform', package / 'build_platform.py')
        status['phase'] = 'prepare_pinned_sources'
        runner.logged([sys.executable, str(package / 'prepare_workspace.py'), '--workspace', str(root)], root, reports / 'r55-targeted-prepare.log')
        runner.logged([sys.executable, str(baseline / 'run_r12.py'), 'apply', '--workspace', str(root), '--stage', 'soc'], root, reports / 'r55-targeted-r13-apply.log')
        helper.verify_applied_writes(baseline, root)
        runner.logged([sys.executable, str(r18 / 'source-fix/apply_soccp.py'), '--soc', str(root / 'vendor/qcom/sm8850')], root, reports / 'r55-targeted-r18-apply.log')
        runner.logged([sys.executable, str(PATCH / 'apply_dsp_auto_boot.py'), '--soc', str(root / 'vendor/qcom/sm8850')], root, reports / 'r55-targeted-dsp-apply.log')
        runner.logged([sys.executable, str(PATCH / 'apply_dsp_auto_boot.py'), '--soc', str(root / 'vendor/qcom/sm8850'), '--check'], root, reports / 'r55-targeted-dsp-check.log')
        source_data = (root / SOURCE).read_bytes()
        status['patched_source_sha256'] = sha(source_data)
        runner.build_targets(root, 'soc')  # Only emits the existing kernel.release filegroup; returned aggregate labels are ignored.
        plan = commands(bazel, options)
        write_json(reports / 'r55-targeted-commands.json', plan)
        status['phase'] = 'compile_pas_and_core'
        write_json(status_path, status)
        runner.logged(plan['build'], root, reports / 'r55-targeted-build.log')
        status['compiled'] = True
        status['phase'] = 'collect_fresh_compiler_outputs'
        result = subprocess.run(plan['cquery'], cwd=root, text=True, capture_output=True)
        (reports / 'r55-targeted-cquery.log').write_text(result.stderr)
        (reports / 'r55-targeted-cquery-outputs.txt').write_text(result.stdout)
        require(result.returncode == 0, 'cquery failed; see diagnostic log')
        # Keep the fresh PAS and core bytes even if a subsequent semantic/action gate fails.
        sys.path.insert(0, str(r18 / 'stage-builder'))
        from elf_contract import parse_elf
        output_owned = True
        module = collect(root, (reports / 'r55-targeted-cquery-outputs.txt').read_text().splitlines(), output, parse_elf)
        require((root / SOURCE).read_bytes() == source_data, 'Patched source changed during build')
        evidence = output / 'evidence'
        evidence.mkdir()
        for src, name in [(root / SOURCE, 'qcom_q6v5_pas.c'), (package / 'sources.lock.json', 'sources.lock.json'),
                          (package / 'build_platform.py', 'prepared-build-platform.py'),
                          (root / 'myron_artifact_metadata/BUILD.bazel', 'kernel-release.BUILD.bazel')]:
            shutil.copy2(src, evidence / name)
        for src in PATCH.iterdir():
            if src.is_file() and src.suffix in ('.py', '.json', '.patch'):
                shutil.copy2(src, evidence / src.name)
        status['phase'] = 'verify_pas_action_inputs'
        result = subprocess.run(plan['aquery'], cwd=root, text=True, capture_output=True)
        (reports / 'r55-targeted-aquery.log').write_text(result.stderr)
        (reports / 'r55-targeted-aquery.json').write_text(result.stdout)
        require(result.returncode == 0, 'aquery failed; see diagnostic log')
        action = action_evidence(json.loads(result.stdout))
        action['source_sha256'] = sha(source_data)
        write_json(reports / 'r55-targeted-action-input.json', action)
        status['phase'] = 'validate_compiled_descriptors'
        runner.logged([sys.executable, str(PATCH / 'check_dsp_auto_boot_elf.py'), '--source', str(root / SOURCE),
                       '--module', str(module), '--report', str(reports / 'r55-targeted-dsp-elf.json')], root, reports / 'r55-targeted-dsp-elf.log')
        status.update(success=True, phase='targeted_pas_verified',
                      limitation='Source-build and descriptor validation only; compatibility with the installed kernel and runtime DSP boot remain unverified.')
    except Exception as error:
        status['error'] = str(error)
        print('R55 STOP:', error, file=sys.stderr)
    finally:
        status['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        write_json(status_path, status)
        if output_owned and output.is_dir() and not output.is_symlink():
            shutil.copy2(status_path, output / status_path.name)
            evidence = output / 'reports'
            evidence.mkdir(exist_ok=True)
            for path in reports.glob('r55-targeted-*'):
                if path.is_file():
                    shutil.copy2(path, evidence / path.name)
            files = []
            for path in sorted(output.rglob('*')):
                if path.is_file() and path.name != 'artifact-lock.json':
                    data = path.read_bytes()
                    files.append({'file': str(path.relative_to(output)), 'bytes': len(data), 'sha256': sha(data)})
            write_json(output / 'artifact-lock.json', {'schema': 1, 'files': files, 'success': status['success']})
    return 0 if status['success'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'package', 'baseline', 'r18'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--ram-mb', type=int, default=10000)
    return run(parser.parse_args())


if __name__ == '__main__':
    sys.exit(main())
