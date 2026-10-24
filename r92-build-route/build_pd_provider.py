#!/usr/bin/env python3
"""Compile R90 plus the repaired ADSP PD provider in one shared kernel build."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
from contract import (BASE_COMMIT, MODULE, PARENT_SHA, PARENT_SOURCE_SHA, PROVIDER,
                      apply, check_overlay, load_r90, parents, pin, r90_snapshot,
                      require, safe, source_contract)

POLICY = {'role': 'validation_only', 'compile_only': True, 'flashable': False,
          'activation_allowed': False, 'runtime_candidate_module_names': [],
          'full_charging_control_enabled': False, 'runtime_abi_compatible': 'NOT_YET_VALIDATED'}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def reconstruct_parent(repo, workspace):
    r90 = load_r90(repo)
    r90.reconstruct_parent(repo, workspace)
    r90.apply(workspace, repo / 'r90-build-route')
    from contract import original_provider
    p = safe(workspace, PROVIDER)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(original_provider(repo))


def load_elf_parser(repo):
    # The same exact R18 parser used by collect_outputs, loaded under a private
    # module name so an unrelated elf_contract cache entry cannot change its API.
    path = safe(repo, 'r92-build-route/reference/r18_elf_parser.py')
    require(pin(path.read_bytes()) == {'bytes': 5082,
        'sha256': '4648bf5a5b45b69d6ad342e5254a65acdec588532fda7cf00e20b82cb778d86c'},
        'Pinned R18 ELF parser changed')
    spec = importlib.util.spec_from_file_location('r92_frozen_r18_elf_parser', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.parse_elf


def verify_compiled_scope(output, repo):
    """Require byte-identical old modules and the new real registration imports."""
    parse_elf = load_elf_parser(repo)
    inventory = json.loads((output / 'module-inventory.json').read_bytes())
    require(inventory['compiled_collection_complete'] is True and inventory['module_count'] == 48,
            'Complete 48-module compiled collection required')
    rows = inventory['modules']
    byname = {row['name']: row for row in rows}
    require(len(byname) == len(rows), 'Duplicate ELF identity')
    reference = json.loads((repo / 'r92-build-route/reference/r90-module-pins.json').read_bytes())
    require(set(byname) == set(reference['modules']) | {MODULE['module_name']}, 'Unexpected compiled scope')
    for name, expected in reference['modules'].items():
        row = byname[name]
        actual = pin(safe(output, row['file']).read_bytes())
        require(actual == expected and actual == {k: row[k] for k in ('bytes', 'sha256')},
                'Original R90 module binary changed: ' + name)
    row = byname[MODULE['module_name']]
    data = safe(output, row['file']).read_bytes()
    require(pin(data) == {k: row[k] for k in ('bytes', 'sha256')}, 'Provider inventory pin mismatch')
    elf = parse_elf(data)
    required_imports = {'protocol_class_pd_register_ops', 'protocol_class_pd_unregister_ops',
                        'mca_adsp_glink_read_prop', 'mca_adsp_glink_write_prop',
                        'mca_event_block_notify_register', 'mca_event_block_notify_unregister'}
    require(required_imports <= elf['imports'], 'Provider registration/cleanup/transport wiring absent')
    dependencies = {'mca_adsp_glink', 'mca_event', 'mca_log', 'mca_protocol_pd_class'}
    require(set(elf['depends']) == dependencies, 'Provider dependency scope changed')
    exports = {}
    for name in dependencies:
        provider = parse_elf(safe(output, byname[name]['file']).read_bytes())
        for symbol, crc in provider['export_crcs'].items():
            require(symbol not in exports, 'Duplicate MCA export')
            exports[symbol] = (name, crc)
    bindings = []
    for symbol in sorted(elf['imports'] & exports.keys()):
        name, crc = exports[symbol]
        require(elf['versions'][symbol] == crc, 'Provider-to-MCA CRC mismatch: ' + symbol)
        bindings.append({'symbol': symbol, 'provider': name, 'crc': hex(crc)})
    require(required_imports <= {r['symbol'] for r in bindings}, 'Required PD provider imports unresolved')
    return {'schema': 1, 'status': 'PASS_R92_EXACT_R90_BINARIES_AND_PD_PROVIDER_WIRING',
            'reference_commit': BASE_COMMIT, 'reference_run_id': reference['github_run_id'],
            'unchanged_R90_module_count': len(reference['modules']), 'added_module': row,
            'actual_provider_imports': sorted(elf['imports']), 'MCA_import_bindings': bindings,
            'hardware_tested': False, 'installed_kernel_full_ABI_review_still_required': True}


class Boundary:
    def __init__(self, repo):
        self.repo = Path(repo).resolve()
        self.route = self.repo / 'r92-build-route'
        self.r90 = load_r90(self.repo)
        self.engine = self.r90.load_engine(self.repo)
        self.parent = self.r90.OverlayBoundary(self.engine, self.repo)
        self.contract = check_overlay(self.repo)
        self.applied = False
        self.finalized = False

    def check(self, repo):
        require(Path(repo).resolve() == self.repo, 'R92 repository changed')
        previous, *rest = self.parent.check(repo)
        self.contract = check_overlay(repo)
        require(previous['validation_only_modules'] + [MODULE] == self.contract['validation_only_modules'],
                'The checked R90 engine scope does not match the exact R92 extension')
        return (self.contract, *rest)

    def verify_all(self, root):
        inherited = self.parent.verify_all(root)
        current = apply(root, self.repo, verify=True)
        return {'schema': 1, 'status': 'PASS_ALL_R90_SOURCES_AND_R92_PD_PROVIDER',
                'inherited': inherited, 'provider': current, 'hardware_tested': False}

    def prebuild_or_postbuild(self, root, repo, pc, parent_inputs, r84, route):
        # The complete unchanged R90 boundary still performs the R88/R89/R90
        # source tests on their own exact production images before R92 applies.
        inherited = self.parent.prebuild_or_postbuild(root, repo, pc, parent_inputs, r84, route)
        reports = root / 'integration-reports'
        write(reports / ('r92-parent-r90-' + ('prebuild' if not self.applied else 'postbuild') + '.json'), inherited)
        if not self.applied:
            require(self.parent.applied and self.parent.verify_calls == 1, 'One complete R90 preparation required')
            write(reports / 'r92-source-apply.json', apply(root, self.repo))
            command = [sys.executable, '-B', str(self.route / 'test_source.py'),
                       '--workspace', str(root), '--output', str(reports / 'r92-host')]
            result = subprocess.run(command, capture_output=True, text=True)
            (reports / 'r92-production-source-tests.log').write_text(result.stdout + result.stderr)
            require(result.returncode == 0, 'R92 actual prepared provider source tests failed')
            self.applied = True
        else:
            require(self.parent.verify_calls == 2, 'Unexpected extra R92 build boundary')
        record = self.verify_all(root)
        write(reports / ('r92-all-' + ('prebuild' if self.parent.verify_calls == 1 else 'postbuild') + '-postimages.json'), record)
        return record

    def finalize(self, output, parent_route, reports, status, config):
        require(self.applied and self.parent.verify_calls == 2 and status.get('success') is True and
                status.get('validation_compiled') is True, 'Complete single-build R92 compile proof required')
        self.verify_all(Path(config['workspace_root']))
        scope = verify_compiled_scope(output, self.repo)
        write(reports / 'r92-compiled-binary-scope.json', scope)
        status.update(round='R92', overlay_applied=True, finalized=True,
            build_contract_sha256=pin((self.route / 'build-contract.json').read_bytes())['sha256'],
            source_contract_sha256=pin((self.route / 'SOURCE-CONTRACT.json').read_bytes())['sha256'],
            parent_build_contract_sha256=PARENT_SHA, parent_source_contract_sha256=PARENT_SOURCE_SHA,
            build_engine='frozen_R88_and_R90_preparation_with_exact_R92_48_target_extension',
            exact_changed_sources=[PROVIDER], added_module_names=[MODULE['module_name']],
            inherited_R90_module_count=47, validation_module_count=48)
        for name in ('artifact-manifest.json', 'module-inventory.json', 'module-identity.json'):
            path = output / name
            record = json.loads(path.read_bytes())
            record.update(POLICY)
            write(path, record)
        shutil.copy2(self.route / 'build-contract.json', output / 'build-contract.json')
        for name in ('r85-build-route', 'r86-build-route', 'r87-build-route', 'r88-build-route',
                     'r89-build-route', 'r90-build-route', 'r92-build-route'):
            shutil.copytree(self.repo / name, output / 'source' / name,
                            ignore=shutil.ignore_patterns('__pycache__'))
        _, parent_source = parents(self.repo)
        snapshots = r90_snapshot(parent_source)
        snapshots[PROVIDER] = source_contract(self.repo)['writes'][0]['after']
        compiled = []
        for name, expected in sorted(snapshots.items()):
            source = safe(Path(config['workspace_root']), name)
            require(pin(source.read_bytes()) == expected, 'Actual compiled source changed: ' + name)
            destination = output / 'compiled-source' / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            compiled.append({'file': str(destination.relative_to(output)), **expected,
                             'role': 'added_provider' if name == PROVIDER else 'unchanged_R90_source'})
        write(reports / 'r92-status.json', status)
        # The inherited filename is retained solely as engine transport.
        write(reports / 'r88-status.json', status)
        write(reports / 'r92-engine-usage.json', {'schema': 1,
            'frozen_R88_engine_sha256': self.r90.ENGINE_SHA,
            'parent_R90_contract_sha256': PARENT_SHA,
            'engine_report_prefix': 'r88-', 'engine_old_phase_labels_do_not_define_R92_module_scope': True,
            'actual_aquery_and_build_targets': 48, 'single_kernel_build': True,
            'all_R90_production_tests_retained': True,
            'new_provider_tested_on_actual_prepared_source_before_compile': True,
            'all_47_R90_module_binary_pins_checked': True})
        destination = output / 'reports'
        destination.mkdir()
        for path in reports.rglob('*'):
            if not path.is_file() or path.suffix not in ('.json', '.log', '.txt'):
                continue
            relative = path.relative_to(reports)
            if any(p.startswith('r92-') for p in relative.parts):
                group = 'r92'
            elif any(p.startswith('r90-') for p in relative.parts):
                group = 'parent-r90'
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
        reference = json.loads((self.route / 'reference/r90-module-pins.json').read_bytes())
        require(pin(config_source.read_bytes()) == reference['effective_config'],
                'Effective module configuration differs from R90')
        config_destination = output / 'module-config/canoe_perf.config'
        config_destination.parent.mkdir()
        shutil.copy2(config_source, config_destination)
        write(output / 'artifact-lock.json', {'schema': 1, **POLICY, 'files': [
            {'file': str(p.relative_to(output)), **pin(p.read_bytes())}
            for p in sorted(output.rglob('*')) if p.is_file()]})
        write(output / 'validation-complete.json', {'schema': 1, **POLICY, 'required_module_count': 48,
            'full_validation_success': True, 'build_contract_sha256': status['build_contract_sha256'],
            'source_contract_sha256': status['source_contract_sha256'], 'compiled_sources': compiled,
            'unchanged_R90_module_count': 47, 'added_module_names': [MODULE['module_name']],
            'artifact_lock_sha256': pin((output / 'artifact-lock.json').read_bytes())['sha256']})
        self.finalized = True

    def install(self):
        self.engine.check = self.check
        self.engine.apply = self.parent.apply_dispatch
        self.engine.verify_postimages = self.prebuild_or_postbuild
        self.engine.finalize = self.finalize


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
    boundary = Boundary(repo)
    if args.check_inputs:
        boundary.check(repo)
        print(json.dumps({'status': 'PASS_R92_AND_FULL_FROZEN_PARENT_INPUTS',
                          'validation_only_count': 48, 'unchanged_R90_modules': 47,
                          'added_module': MODULE['module_name']}))
        return 0
    require(args.workspace is not None, '--workspace required')
    root = args.workspace.resolve()
    output = root / 'integration-artifacts/r92-mca-validation-only'
    require(not output.exists() and not output.is_symlink(), 'Fresh R92 output path required')
    boundary.install()
    result = boundary.engine.main()
    status_path = root / 'integration-reports/r88-status.json'
    status = json.loads(status_path.read_bytes()) if status_path.exists() else {'success': False}
    status.update(round='R92', parent_build_contract_sha256=PARENT_SHA,
                  parent_source_contract_sha256=PARENT_SOURCE_SHA,
                  build_contract_sha256=pin((boundary.route / 'build-contract.json').read_bytes())['sha256'],
                  source_contract_sha256=pin((boundary.route / 'SOURCE-CONTRACT.json').read_bytes())['sha256'],
                  exact_changed_sources=[PROVIDER], overlay_applied=boundary.applied,
                  finalized=boundary.finalized, validation_module_count=48)
    if result == 0:
        try:
            require(boundary.finalized, 'Engine success without R92 finalization is invalid')
            (root / 'integration-artifacts/r88-mca-validation-only').rename(output)
        except Exception as error:
            status.update(success=False, phase='finalize_output_failed', error=str(error))
            result = 1
    write(root / 'integration-reports/r92-status.json', status)
    return result


if __name__ == '__main__':
    sys.exit(main())
