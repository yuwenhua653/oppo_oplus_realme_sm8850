#!/usr/bin/env python3
"""Apply R89 then R90 at the pinned R88 prebuild boundary; compile the same closure once."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
from apply_temp_schema import (PARENT_SHA, PARENT_SOURCE_SHA, WRITES, apply,
                                  check_overlay, parent_contracts, parent_snapshot_pins,
                                  pin, require, safe, source_contract)

ENGINE_SHA = '5341b707f8c318d3836936229b919a1bd2bad8c810b32c67b2cb91e6f0d9f591'
POLICY = {'role': 'validation_only', 'compile_only': True, 'flashable': False,
          'activation_allowed': False, 'runtime_candidate_module_names': [],
          'full_charging_control_enabled': False, 'runtime_abi_compatible': 'NOT_YET_VALIDATED'}


def write(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')


def load_engine(repo):
    path = repo / 'r88-build-route/build_fg_policy.py'
    require(pin(path.read_bytes())['sha256'] == ENGINE_SHA, 'Frozen R88 build engine changed')
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location('r90_frozen_r88_engine', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_r89(repo):
    path = repo / 'r89-build-route/apply_probe_recovery.py'
    require(pin(path.read_bytes())['sha256'] ==
            'e91e467e54286bb53279e54934624fe3813778682eda3b951a9a646a10cee304',
            'Frozen R89 preparation helper changed')
    spec = importlib.util.spec_from_file_location('r90_frozen_r89_preparation', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.check_overlay(repo)
    return module


def reconstruct_parent(repo, workspace):
    """Reproduce the pinned R89 source snapshot locally without network or compilation."""
    engine = load_engine(repo)
    r89 = load_r89(repo)
    _, r88_source = r89.parent_contracts(repo)
    path = repo / 'r88-build-route/test_source.py'
    spec = importlib.util.spec_from_file_location('r90_parent_snapshot', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.reconstruct_inputs(repo, workspace, r88_source)
    engine.apply(workspace, repo / 'r88-build-route')
    r89.apply(workspace, repo / 'r89-build-route')
    _, r89_source = parent_contracts(repo)
    for name, expected in parent_snapshot_pins(r89_source).items():
        require(pin(safe(workspace, name).read_bytes()) == expected, 'Wrong reconstructed R89 source: ' + name)


class OverlayBoundary:
    """Keep R88 preparation/tests/aquery/compile intact and own changed-source validation."""
    def __init__(self, engine, repo):
        self.engine, self.repo = engine, repo
        self.route = repo / 'r90-build-route'
        self.contract = check_overlay(repo)
        self.source = source_contract(self.route)
        self.r89 = load_r89(repo)
        self.parent_check = engine.check
        self.parent_apply = engine.apply
        self.parent_verify = engine.verify_postimages
        self.applied = False
        self.verify_calls = 0
        self.finalized = False

    def check(self, repo):
        require(Path(repo).resolve() == self.repo, 'R90 repository changed')
        previous, *rest = self.parent_check(repo)
        require(pin((repo / 'r89-build-route/build-contract.json').read_bytes())['sha256'] == PARENT_SHA,
                'R89 parent contract changed')
        # check_overlay verifies identical module labels, source lists, core targets,
        # retained kernel, configurations and frozen repository/toolchain revisions.
        self.r89.check_overlay(repo)
        self.contract = check_overlay(repo)
        return (self.contract, *rest)

    def apply_dispatch(self, root, route, verify=False):
        if not self.applied:
            return self.parent_apply(root, route, verify=verify)
        require(verify, 'R88 preparation cannot run after the R90 boundary')
        return self.verify_all(root)

    def verify_all(self, root):
        expected = self.engine.parent_postimages(self.repo)
        _, r88_source = self.r89.parent_contracts(self.repo)
        _, r89_source = parent_contracts(self.repo)
        for round_name, source in [('R88', r88_source), ('R89', r89_source)]:
            for row in source['writes']:
                require(expected.get(row['path']) == row['before']['sha256'], round_name + ' ancestry mismatch')
                expected[row['path']] = row['after']['sha256']
        for row in self.source['writes']:
            require(expected.get(row['path']) == row['before']['sha256'], 'R90 ancestry mismatch')
            expected[row['path']] = row['after']['sha256']
        for name, digest in expected.items():
            require(pin(safe(root, name).read_bytes())['sha256'] == digest,
                    'Integrated inherited/R90 source changed: ' + name)
        apply(root, self.route, verify=True)
        return {'schema': 1, 'status': 'PASS_ALL_INHERITED_AND_R90_POSTIMAGES',
                'checked_destinations': len(expected), 'exact_R90_overlays': sorted(WRITES),
                'unchanged_R89_destination_count': len(expected) - len(WRITES),
                'hardware_tested': False}

    def prebuild_or_postbuild(self, root, repo, pc, parent_inputs, r84, route):
        self.verify_calls += 1
        reports = root / 'integration-reports'
        if not self.applied:
            require(self.verify_calls == 1, 'One R90 prebuild boundary required')
            # Called only after the unchanged R88 main has run R85/R86/R87/R88
            # production suites on their own exact prepared postimages.
            original = self.parent_verify(root, repo, pc, parent_inputs, r84, route)
            write(reports / 'r90-parent-r88-postimages.json', original)
            write(reports / 'r90-parent-r89-apply.json', self.r89.apply(root, self.repo / 'r89-build-route'))
            write(reports / 'r90-parent-r89-check.json', self.r89.apply(root, self.repo / 'r89-build-route', verify=True))
            parent_command = [sys.executable, '-B', str(self.repo / 'r89-build-route/test_source.py'),
                              '--workspace', str(root), '--output', str(reports / 'r90-parent-r89-host')]
            parent_result = subprocess.run(parent_command, capture_output=True, text=True)
            (reports / 'r90-parent-r89-production-source-tests.log').write_text(parent_result.stdout + parent_result.stderr)
            require(parent_result.returncode == 0, 'R89 actual prepared source tests failed')
            write(reports / 'r90-source-apply.json', apply(root, self.route))
            write(reports / 'r90-source-check.json', apply(root, self.route, verify=True))
            command = [sys.executable, '-B', str(self.route / 'test_source.py'),
                       '--workspace', str(root), '--output', str(reports / 'r90-host')]
            result = subprocess.run(command, capture_output=True, text=True)
            (reports / 'r90-production-source-tests.log').write_text(result.stdout + result.stderr)
            require(result.returncode == 0, 'R90 actual prepared source tests failed')
            self.applied = True
        else:
            require(self.verify_calls == 2, 'Unexpected additional engine verification boundary')
        record = self.verify_all(root)
        write(reports / ('r90-all-' + ('prebuild' if self.verify_calls == 1 else 'postbuild') + '-postimages.json'), record)
        return record

    def finalize(self, output, parent_route, reports, status, config):
        require(self.applied and self.verify_calls == 2 and status.get('success') is True and
                status.get('validation_compiled') is True, 'Complete R90 compile proof required')
        self.verify_all(Path(config['workspace_root']))
        status.update(round='R90', overlay_applied=True, finalized=True,
                      build_contract_sha256=pin((self.route / 'build-contract.json').read_bytes())['sha256'],
                      source_contract_sha256=pin((self.route / 'SOURCE-CONTRACT.json').read_bytes())['sha256'],
                      parent_build_contract_sha256=PARENT_SHA, parent_source_contract_sha256=PARENT_SOURCE_SHA,
                      build_engine='frozen_R88_with_verified_R89_then_R90_overlay_boundary',
                      exact_changed_sources=sorted(WRITES))
        for name in ('artifact-manifest.json', 'module-inventory.json', 'module-identity.json'):
            path = output / name
            record = json.loads(path.read_bytes())
            record.update(POLICY)
            write(path, record)
        require(json.loads((output / 'module-inventory.json').read_bytes())['module_count'] == 47,
                'Final R90 inventory must contain all 47 inactive modules')
        shutil.copy2(self.route / 'build-contract.json', output / 'build-contract.json')
        for name in ('r85-build-route', 'r86-build-route', 'r87-build-route', 'r88-build-route', 'r89-build-route', 'r90-build-route'):
            shutil.copytree(self.repo / name, output / 'source' / name,
                            ignore=shutil.ignore_patterns('__pycache__'))
        _, parent_source = parent_contracts(self.repo)
        snapshots = parent_snapshot_pins(parent_source)
        for row in self.source['writes']:
            snapshots[row['path']] = row['after']
        compiled = []
        for name, expected in sorted(snapshots.items()):
            source = safe(Path(config['workspace_root']), name)
            require(pin(source.read_bytes()) == expected, 'Actual compiled R90 source changed: ' + name)
            destination = output / 'compiled-source' / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            compiled.append({'file': str(destination.relative_to(output)), **expected,
                             'role': 'changed' if name in WRITES else 'unchanged_R89_guard'})
        write(reports / 'r90-status.json', status)
        # The engine wrote this filename just before calling finalization. Update
        # it before snapshotting reports so it cannot retain stale R88 hashes.
        write(reports / 'r88-status.json', status)
        write(reports / 'r90-engine-usage.json', {
            'schema': 1, 'engine_sha256': ENGINE_SHA, 'engine_contract_sha256': self.r89.PARENT_SHA, 'parent_R89_contract_sha256': PARENT_SHA,
            'engine_report_prefix': 'r88-', 'engine_prefix_is_not_a_claim_of_unchanged_R88_sources': True,
            'R88_and_R89_production_tests_before_R90_overlay': True, 'R90_production_tests_before_compile': True,
            'aquery_action_chain_effective_config_and_47_module_collection': 'unchanged_pinned_R88_engine',
            'exact_changed_sources': sorted(WRITES)})
        destination = output / 'reports'
        destination.mkdir()
        for path in reports.rglob('*'):
            if not path.is_file() or path.suffix not in ('.json', '.log', '.txt'):
                continue
            relative = path.relative_to(reports)
            if any(p.startswith('r90-') for p in relative.parts):
                group = 'r90'
            elif any(p.startswith('r88-') for p in relative.parts):
                group = 'inherited-engine'
            else:
                continue
            target = destination / group / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        config_source = Path(config['workspace_root']) / config['config_path']
        require(pin(config_source.read_bytes()) == {k: config[k] for k in ('bytes', 'sha256')},
                'Effective module config changed during finalization')
        config_destination = output / 'module-config/canoe_perf.config'
        config_destination.parent.mkdir()
        shutil.copy2(config_source, config_destination)
        write(output / 'artifact-lock.json', {'schema': 1, **POLICY, 'files': [
            {'file': str(p.relative_to(output)), **pin(p.read_bytes())}
            for p in sorted(output.rglob('*')) if p.is_file()]})
        write(output / 'validation-complete.json', {'schema': 1, **POLICY, 'required_module_count': 47,
            'full_validation_success': True, 'build_contract_sha256': status['build_contract_sha256'],
            'source_contract_sha256': status['source_contract_sha256'], 'compiled_sources': compiled,
            'artifact_lock_sha256': pin((output / 'artifact-lock.json').read_bytes())['sha256']})
        self.finalized = True

    def install(self):
        self.engine.check = self.check
        self.engine.apply = self.apply_dispatch
        self.engine.verify_postimages = self.prebuild_or_postbuild
        self.engine.finalize = self.finalize


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo-root', type=Path, required=True)
    p.add_argument('--check-inputs', action='store_true')
    p.add_argument('--check-overlay', action='store_true')
    for name in ('workspace', 'package', 'baseline', 'r18'):
        p.add_argument('--' + name, type=Path)
    p.add_argument('--jobs', type=int, default=2)
    p.add_argument('--ram-mb', type=int, default=10000)
    args = p.parse_args()
    repo = args.repo_root.resolve()
    contract = check_overlay(repo)
    if args.check_overlay:
        print(json.dumps({'status': 'PASS_R90_OVERLAY_INPUTS_ONLY',
                          'locked_inputs': len(contract['locked_files']), 'full_parent_chain_checked': False}))
        return 0
    engine = load_engine(repo)
    boundary = OverlayBoundary(engine, repo)
    if args.check_inputs:
        boundary.check(repo)
        print(json.dumps({'status': 'PASS_R90_AND_FULL_FROZEN_PARENT_INPUTS',
                          'locked_inputs': len(contract['locked_files']), 'validation_only_count': 47}))
        return 0
    require(args.workspace is not None, '--workspace required')
    root = args.workspace.resolve()
    output = root / 'integration-artifacts/r90-mca-validation-only'
    require(not output.exists() and not output.is_symlink(), 'Fresh R90 output path required')
    boundary.install()
    result = engine.main()
    engine_status = root / 'integration-reports/r88-status.json'
    status = json.loads(engine_status.read_bytes()) if engine_status.exists() else {'success': False}
    status.update(round='R90', parent_build_contract_sha256=PARENT_SHA,
                  parent_source_contract_sha256=PARENT_SOURCE_SHA, engine_sha256=ENGINE_SHA,
                  build_contract_sha256=pin((repo / 'r90-build-route/build-contract.json').read_bytes())['sha256'],
                  source_contract_sha256=pin((repo / 'r90-build-route/SOURCE-CONTRACT.json').read_bytes())['sha256'],
                  exact_changed_sources=sorted(WRITES), overlay_applied=boundary.applied,
                  finalized=boundary.finalized)
    if result == 0:
        try:
            require(boundary.finalized, 'Engine success without R90 finalization is invalid')
            (root / 'integration-artifacts/r88-mca-validation-only').rename(output)
        except Exception as error:
            status.update(success=False, phase='finalize_output_failed', error=str(error))
            result = 1
    write(root / 'integration-reports/r90-status.json', status)
    return result


if __name__ == '__main__':
    sys.exit(main())
