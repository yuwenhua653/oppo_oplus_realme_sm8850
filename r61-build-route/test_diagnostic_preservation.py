#!/usr/bin/env python3
"""Offline regression of the actual build main() and artifact collector.

Only external preparation/build programs and ELF decoding are substituted.
The real source-contract checker, integrated source locks, 15-module aquery
provenance, collector, manifests, and exit status run against temporary files.
No kernel build, ABI compatibility, or device behavior is claimed.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROUTE = HERE if (HERE / 'targeted_battery_build.py').is_file() else HERE / 'r61-build-route'
REVIEW_ROOT = ROUTE.parent
SUPPORT = REVIEW_ROOT.parent / 'candidate/r61-build-route'
WORKFLOW = REVIEW_ROOT / '.github/workflows/build-myron-battery-r61.yml'
NAMES = [
    'charger_partition', 'mca_basic_wireless', 'mca_buckchg_jeita',
    'mca_business_charger_comp', 'mca_charger_thermal', 'mca_qcom_sysfs',
    'mca_quick_wireless', 'mca_smart_charge', 'mca_strategy_buckchg',
    'mca_strategy_fg_comp', 'mca_strategy_quickchg', 'bq27z561', 'camera', 'sc8581', 'mca_qcom_subpmic_proxy',
]
DIAGNOSTIC_NAMES = {'bq27z561', 'camera'}
AUXILIARY_NAMES = ['mca_platform_cp_class', 'mca_platform_buckchg_class', 'mca_platform_fg_ic_ops']
DIAGNOSTIC_AUXILIARY = {'mca_platform_fg_ic_ops'}
RELEASE = '6.12.81-android16-6-maybe-dirty-4k'
BASELINE_IMAGE_SHA = '2fa774b4ffdd75064fb733bb2cad071b02b1813ad5cd54bae32bda2247ef18a7'
BIN = 'bazel-out/aarch64-fastbuild/bin/'
DEPENDENCY = BIN + 'vendor/dependency/Module.symvers'
UNRELATED_KO = BIN + 'vendor/unrequested/unrequested.ko'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def load_implementation():
    # The prepared review bundle may contain only the changed driver; unchanged
    # source-validation helpers are then read from the neighboring candidate.
    with patch.object(sys, 'path', [str(ROUTE), str(SUPPORT)] + sys.path):
        spec = importlib.util.spec_from_file_location(
            'diagnostic_preservation_target', ROUTE / 'targeted_battery_build.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class BuildFixture:
    def __init__(self, base, implementation, failure=None):
        self.base = base
        self.impl = implementation
        self.failure = failure
        self.fail_finalization = False
        self.workspace = base / 'workspace with spaces'
        self.repo = base / 'repo'
        self.package = base / 'package'
        self.baseline = base / 'baseline'
        self.r18 = base / 'r18'
        for path in (self.workspace, self.repo, self.package, self.baseline, self.r18):
            path.mkdir()
        self.events = []
        self.builds = []
        self.locked = []
        self.modules = []
        self.auxiliary = []
        self.integrated = []
        writes = []
        for name in NAMES + AUXILIARY_NAMES:
            source = 'vendor/fixture/' + name + '.c'
            data = ('/* reviewed source: ' + name + ' */\n').encode()
            self.write_workspace(source, data)
            postimage = 'payload/' + name + '.c'
            self.lock_file(postimage, data)
            self.integrated.append({'path': source, 'sha256': sha(data)})
            writes.append({'source': postimage, 'destination': source,
                           'before_sha256': None, 'preimage': None,
                           'after_sha256': sha(data)})
            row = {'module_name': name, 'target': '//vendor/fixture:' + name,
                   'output': BIN + 'vendor/fixture/' + name + '/' + name + '.ko',
                   'symvers': BIN + 'vendor/fixture/' + name + '/Module.symvers',
                   'expected_sources': [source]}
            (self.modules if name in NAMES else self.auxiliary).append(row)
        self.generated = {'source': 'common/drivers/scsi/sd.h',
                          'output': BIN + 'vendor/fixture/drivers/scsi/sd.h'}
        self.modules[0]['generated_inputs'] = [self.generated['output']]
        self.header = b'/* pinned private sd.h fixture */\n'
        self.write_workspace(self.generated['source'], self.header)
        self.lock_file('upstream/sd.h', self.header)
        prior_data = b'/* unchanged prerequisite source */\n'
        self.write_workspace('vendor/prior.c', prior_data)
        prior = {'schema': 1, 'integration': {'script': 'prior/apply.py'},
                 'workspace_files': [{'path': 'vendor/prior.c', 'sha256': sha(prior_data)}]}
        self.lock_file('prior/contract.json', json.dumps(prior).encode())
        self.lock_file('reviewed-scope.json', json.dumps({'reviewed_module_names': NAMES, 'reviewed_auxiliary_provider_names': AUXILIARY_NAMES, 'diagnostic_auxiliary_provider_names': sorted(DIAGNOSTIC_AUXILIARY)}).encode())
        self.lock_file('apply.py', b'# external integration fixture\n')
        write_lock = {'schema': 1, 'git_heads': {'common': 'fixture-pinned-revision'},
                      'writes': writes, 'upstream_files': [
                          {'repo': 'common', 'path': 'drivers/scsi/sd.h',
                           'source': 'upstream/sd.h', 'sha256': sha(self.header)}]}
        self.lock_file('write-lock.json', json.dumps(write_lock).encode())
        self.contract = {
            'schema': 1, 'source_review': 'PASS', 'compile_only': True,
            'flashable': False, 'baseline_kernel_release': RELEASE,
            'baseline_image_sha256': BASELINE_IMAGE_SHA,
            'remote_base_commit': 'e00bebf6b5bc64ae277b7f52af0eb292744834dc',
            'prerequisite_contract': 'prior/contract.json',
            'integration': {'script': 'apply.py', 'lock': 'write-lock.json'},
            'scope_manifest': 'reviewed-scope.json', 'locked_files': self.locked,
            'workspace_files': self.integrated, 'modules': self.modules,
            'auxiliary_providers': self.auxiliary, 'diagnostic_auxiliary_providers': sorted(DIAGNOSTIC_AUXILIARY),
            'generated_files': [self.generated],
        }
        self.contract_path = self.repo / 'battery-contract.json'
        write_json(self.contract_path, self.contract)
        self.output = self.workspace / 'integration-artifacts/r61-targeted-battery'
        self.diagnostic = self.workspace / 'integration-artifacts/r61-targeted-diagnostic'
        self.reports = self.workspace / 'integration-reports'
        self.graph = self.make_graph()
        self.runner = SimpleNamespace(logged=self.logged, build_targets=self.build_targets)
        self.helper = SimpleNamespace(
            verify_bundle=lambda baseline, runner: (b'fixture runner', {'verified': True}),
            runner_build_configuration=lambda data, root, jobs, ram: (['fixture-bazel'], []),
            verify_applied_writes=lambda baseline, root: None,
        )

    def write_workspace(self, name, data):
        path = self.workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def lock_file(self, name, data):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.locked.append({'path': name, 'sha256': sha(data), 'bytes': len(data)})

    def make_graph(self):
        graph = {'artifacts': [], 'depSetOfFiles': [], 'actions': []}
        ids = {}

        def artifact(name):
            if name not in ids:
                ids[name] = str(len(ids) + 1)
                graph['artifacts'].append({'id': ids[name], 'execPath': name})
            return ids[name]

        for index, row in enumerate(self.modules + self.auxiliary, 1):
            inputs = row['expected_sources'] + row.get('generated_inputs', [])
            graph['depSetOfFiles'].append({'id': str(index),
                                          'directArtifactIds': [artifact(n) for n in inputs]})
            graph['actions'].append({'mnemonic': 'KernelModule',
                                     'actionKey': 'fixture-action-' + row['module_name'],
                                     'inputDepSetIds': [str(index)],
                                     'outputIds': [artifact(row['output']), artifact(row['symvers'])]})
        graph['actions'].append({'mnemonic': 'CopyHeader',
                                 'outputIds': [artifact(self.generated['output'])]})
        return graph

    def load(self, name, path):
        if name == 'r61_prior_check':
            # Prerequisite integration checking belongs to the external R60
            # preparation route; the current R61 checker is not mocked.
            return SimpleNamespace(check=lambda root, contract: None)
        if name == 'r61_r18':
            return SimpleNamespace(verify_bundle=lambda: 'fixture-r18-lock')
        if name == 'r61_driver':
            return self.helper
        if name == 'r61_platform':
            return self.runner
        raise AssertionError('Unexpected external loader: ' + name)

    def build_targets(self, root, stage):
        assert root == self.workspace and stage == 'soc'
        self.events.append('prepare-release-target')

    def selected(self, argv):
        command = ' '.join(argv)
        return [row for row in self.modules if row['target'] in command]

    def assert_analysis_complete(self):
        actions = sorted(self.reports.glob('r61-targeted-action-*.json'))
        assert len(actions) == len(NAMES) + len(AUXILIARY_NAMES), 'Build started before all 15 target and 3 provider action guards'
        assert all(json.loads(path.read_text())['status'] == 'PASS' for path in actions)
        assert self.events.index('aquery-15') < len(self.events)

    def produce(self, modules, full):
        selected_auxiliary = [row for row in self.auxiliary if full or row['module_name'] in DIAGNOSTIC_AUXILIARY]
        for row in modules + selected_auxiliary:
            # Decoding alone is stubbed: copied bytes and SHA records stay real.
            self.write_workspace(row['output'], ('ELF-FIXTURE:' + row['module_name']).encode())
            self.write_workspace(row['symvers'], ('symvers:' + row['module_name'] + '\n').encode())
        self.write_workspace(DEPENDENCY, b'0x12345678\tdependency_export\tdependency\tEXPORT_SYMBOL\n')
        self.write_workspace(UNRELATED_KO, b'unrequested KO must not be collected')
        for name in self.impl.CORE_REQUIRED:
            data = (RELEASE + '\n').encode() if name == 'include/config/kernel.release' else ('core:' + name).encode()
            self.write_workspace(self.impl.CORE + name, data)
        if full:
            self.write_workspace(self.generated['output'], self.header)

    def logged(self, argv, root, log):
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text('offline external command fixture\n')
        if argv[:2] != ['fixture-bazel', 'build']:
            self.events.append('prepare')
            return
        self.assert_analysis_complete()
        selected = self.selected(argv)
        names = {row['module_name'] for row in selected}
        self.builds.append(names)
        full = names == set(NAMES)
        assert names == (set(NAMES) if len(self.builds) == 2 else DIAGNOSTIC_NAMES)
        assert '//common:kernel_aarch64' in argv
        assert '//myron_artifact_metadata:kernel_release' in argv
        self.events.append('build-full' if full else 'build-diagnostic')
        if not full:
            assert not (self.workspace / self.generated['output']).exists(), 'Diagnostic unexpectedly depends on sd.h'
        if self.failure == ('full' if full else 'diagnostic'):
            if not full:
                # A partial compiler output does not authorize publication.
                self.write_workspace(selected[0]['output'], b'partial compiler output')
            raise RuntimeError('simulated later MCA failure' if full else 'simulated diagnostic build failure')
        self.produce(selected, full)

    def subprocess_run(self, argv, **kwargs):
        assert argv[0] == 'fixture-bazel', 'Unexpected subprocess: ' + repr(argv)
        assert kwargs['cwd'] == self.workspace
        if argv[1] == 'aquery':
            assert {row['module_name'] for row in self.selected(argv)} == set(NAMES)
            self.events.append('aquery-15')
            stdout = json.dumps(self.graph)
        elif argv[1] == 'cquery':
            selected = self.selected(argv)
            full = len(selected) == len(NAMES)
            self.events.append('cquery-full' if full else 'cquery-diagnostic')
            selected_auxiliary = [row for row in self.auxiliary if full or row['module_name'] in DIAGNOSTIC_AUXILIARY]
            candidates = [row[key] for row in selected + selected_auxiliary for key in ('output', 'symvers')]
            if self.failure == 'missing_auxiliary' and not full:
                candidates.remove(selected_auxiliary[0]['output'])
            candidates += [self.impl.CORE + name for name in sorted(self.impl.CORE_REQUIRED)]
            candidates += [DEPENDENCY, UNRELATED_KO, DEPENDENCY]
            if not full and self.failure == 'missing_core':
                candidates.remove(self.impl.CORE + 'Image')
            if full:
                candidates.append(self.generated['output'])
            stdout = '\n'.join(candidates) + '\n'
        else:
            raise AssertionError('Unexpected Bazel command: ' + repr(argv))
        return subprocess.CompletedProcess(argv, 0, stdout, '')

    def run(self):
        elf = ModuleType('elf_contract')
        real_copy2 = self.impl.shutil.copy2

        def copy2(source, destination, **kwargs):
            if self.fail_finalization and Path(destination) == self.diagnostic / 'battery-contract.json':
                raise OSError('simulated final diagnostic contract copy failure')
            return real_copy2(source, destination, **kwargs)

        def parse_elf(data):
            assert data.startswith(b'ELF-FIXTURE:')
            return {'name': data.decode().split(':', 1)[1],
                    'info': {'vermagic': [RELEASE + ' SMP preempt mod_unload aarch64']}}

        elf.parse_elf = parse_elf
        argv = ['targeted_battery_build.py']
        for key, value in [('workspace', self.workspace), ('package', self.package),
                           ('baseline', self.baseline), ('r18', self.r18),
                           ('repo-root', self.repo), ('contract', self.contract_path)]:
            argv.extend(['--' + key, str(value)])
        with patch.object(sys, 'argv', argv), patch.object(self.impl, 'load', self.load), \
                patch.object(self.impl.subprocess, 'run', self.subprocess_run), \
                patch.object(self.impl.shutil, 'copy2', copy2), \
                patch.dict(sys.modules, {'elf_contract': elf}), \
                patch.object(sys, 'path', list(sys.path)), contextlib.redirect_stderr(io.StringIO()):
            return self.impl.main()


class DiagnosticPreservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.impl = load_implementation()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='r61-diagnostic-main-')
        self.addCleanup(self.temporary.cleanup)

    def fixture(self, failure=None):
        return BuildFixture(Path(self.temporary.name), self.impl, failure)

    def assert_records(self, directory, records):
        for row in records:
            data = (directory / row['file']).read_bytes()
            self.assertEqual(row['bytes'], len(data))
            self.assertEqual(row['sha256'], sha(data))

    def assert_diagnostic(self, fixture, full_success=False):
        manifest = json.loads((fixture.diagnostic / 'diagnostic-manifest.json').read_text())
        self.assertTrue(manifest['compile_only'])
        self.assertFalse(manifest['flashable'])
        self.assertEqual(manifest['full_build_not_passed'], not full_success)
        self.assertEqual(manifest['scope'], 'diagnostic_subset')
        self.assertTrue(manifest['partial'])
        self.assertTrue(manifest['compiled'])
        self.assertTrue(manifest['validated_subset'])
        self.assertFalse(manifest['hardware_tested'])
        self.assertEqual(manifest['runtime_abi_compatible'], 'NOT_YET_VALIDATED')
        self.assertEqual(manifest['full_module_count'], len(NAMES))
        self.assertEqual(manifest['built_image_sha256'],
                         sha((fixture.diagnostic / 'objects' / self.impl.CORE / 'Image').read_bytes()))
        self.assertFalse(manifest['built_image_matches_runtime_baseline'])
        self.assertEqual(set(manifest['selected_module_names']), DIAGNOSTIC_NAMES)
        self.assertEqual(manifest['missing'], [])
        sources = {row['source'] for row in manifest['files']}
        expected = {row[key] for row in fixture.modules if row['module_name'] in DIAGNOSTIC_NAMES
                    for key in ('output', 'symvers')}
        expected |= {row[key] for row in fixture.auxiliary if row['module_name'] in DIAGNOSTIC_AUXILIARY for key in ('output', 'symvers')}
        self.assertEqual(set(manifest['auxiliary_provider_names']), DIAGNOSTIC_AUXILIARY)
        expected |= {self.impl.CORE + name for name in self.impl.CORE_REQUIRED} | {DEPENDENCY}
        self.assertEqual(sources, expected)
        self.assert_records(fixture.diagnostic, manifest['files'])
        self.assertNotIn(fixture.generated['output'], sources)
        self.assertNotIn(UNRELATED_KO, sources)
        identities = json.loads((fixture.diagnostic / 'module-identity.json').read_text())
        self.assertEqual({row['name'] for row in identities['modules']}, DIAGNOSTIC_NAMES)
        self.assertEqual({row['name'] for row in identities['auxiliary_providers']}, DIAGNOSTIC_AUXILIARY)
        self.assertEqual(identities['runtime_abi_compatible'], 'NOT_YET_VALIDATED')
        lock = json.loads((fixture.diagnostic / 'artifact-lock.json').read_text())
        self.assertEqual(lock['scope'], 'diagnostic_subset')
        self.assertEqual(lock['full_build_not_passed'], not full_success)
        self.assert_records(fixture.diagnostic, lock['files'])
        self.assertEqual(manifest['source_contract_sha256'], sha(fixture.contract_path.read_bytes()))
        completion = json.loads((fixture.diagnostic / 'diagnostic-complete.json').read_text())
        self.assertEqual(completion['scope'], 'diagnostic_subset')
        self.assertTrue(completion['compile_only'])
        self.assertEqual(completion['full_build_not_passed'], not full_success)
        self.assertEqual(completion['runtime_abi_compatible'], 'NOT_YET_VALIDATED')
        self.assertEqual(completion['artifact_lock_sha256'],
                         sha((fixture.diagnostic / 'artifact-lock.json').read_bytes()))
        self.assertEqual(completion['diagnostic_manifest_sha256'],
                         sha((fixture.diagnostic / 'diagnostic-manifest.json').read_bytes()))
        self.assertFalse((fixture.diagnostic / 'diagnostic-complete.tmp').exists())
        return manifest

    def test_full_success_preserves_independent_diagnostic_subset(self):
        fixture = self.fixture()
        self.assertEqual(fixture.run(), 0)
        self.assertEqual(fixture.builds, [DIAGNOSTIC_NAMES, set(NAMES)])
        self.assert_diagnostic(fixture, full_success=True)
        status = json.loads((fixture.reports / 'r61-targeted-status.json').read_text())
        self.assertTrue(status['success'])
        self.assertTrue(status['compiled'])
        full = json.loads((fixture.output / 'module-identity.json').read_text())
        self.assertEqual({row['name'] for row in full['modules']}, set(NAMES))
        self.assertEqual({row['name'] for row in full['auxiliary_providers']}, set(AUXILIARY_NAMES))
        artifacts = json.loads((fixture.output / 'artifact-manifest.json').read_text())
        self.assertIn(fixture.generated['output'], {row['source'] for row in artifacts['files']})
        self.assert_records(fixture.output, artifacts['files'])
        self.assertTrue(json.loads((fixture.output / 'artifact-lock.json').read_text())['success'])

    def test_later_mca_failure_preserves_subset_without_full_success(self):
        fixture = self.fixture('full')
        self.assertEqual(fixture.run(), 1)
        self.assertEqual(fixture.builds, [DIAGNOSTIC_NAMES, set(NAMES)])
        self.assert_diagnostic(fixture)
        self.assertFalse((fixture.workspace / fixture.generated['output']).exists())
        status = json.loads((fixture.reports / 'r61-targeted-status.json').read_text())
        self.assertFalse(status['success'])
        self.assertFalse(status['compiled'])
        self.assertIn('later MCA failure', status['error'])
        self.assertFalse((fixture.output / 'artifact-manifest.json').exists())
        self.assertFalse((fixture.output / 'module-identity.json').exists())
        self.assertFalse((fixture.output / 'artifact-lock.json').exists())

    def test_initial_diagnostic_build_failure_has_no_publishable_manifest(self):
        fixture = self.fixture('diagnostic')
        # A previous run's marker must not survive a new failed run.
        write_json(fixture.diagnostic / 'diagnostic-manifest.json', {'stale': True})
        write_json(fixture.diagnostic / 'diagnostic-complete.json', {'stale': True})
        write_json(fixture.output / 'artifact-manifest.json', {'stale': True})
        self.assertEqual(fixture.run(), 1)
        self.assertEqual(fixture.builds, [DIAGNOSTIC_NAMES])
        self.assertFalse((fixture.diagnostic / 'diagnostic-manifest.json').exists())
        self.assertFalse((fixture.diagnostic / 'diagnostic-complete.json').exists())
        self.assertFalse((fixture.output / 'artifact-manifest.json').exists())
        status = json.loads((fixture.reports / 'r61-targeted-status.json').read_text())
        self.assertFalse(status['success'])
        self.assertFalse(status['compiled'])
        self.assertIn('diagnostic build failure', status['error'])

    def test_diagnostic_missing_core_has_no_publishable_manifest(self):
        fixture = self.fixture('missing_core')
        self.assertEqual(fixture.run(), 1)
        self.assertEqual(fixture.builds, [DIAGNOSTIC_NAMES])
        self.assertIn('cquery-diagnostic', fixture.events)
        self.assertFalse((fixture.diagnostic / 'diagnostic-manifest.json').exists())
        self.assertFalse((fixture.diagnostic / 'diagnostic-complete.json').exists())
        self.assertFalse((fixture.diagnostic / 'artifact-lock.json').exists())
        self.assertFalse((fixture.output / 'artifact-manifest.json').exists())
        status = json.loads((fixture.reports / 'r61-targeted-status.json').read_text())
        self.assertFalse(status['success'])
        self.assertFalse(status.get('diagnostic_subset_verified', False))
        self.assertIn('Required compiler output missing', status['error'])

    def test_diagnostic_missing_provider_has_no_publishable_manifest(self):
        fixture = self.fixture('missing_auxiliary')
        self.assertEqual(fixture.run(), 1)
        self.assertEqual(fixture.builds, [DIAGNOSTIC_NAMES])
        self.assertFalse((fixture.diagnostic / 'diagnostic-manifest.json').exists())
        self.assertFalse((fixture.diagnostic / 'diagnostic-complete.json').exists())
        status = json.loads((fixture.reports / 'r61-targeted-status.json').read_text())
        self.assertIn('Required compiler output missing', status['error'])

    def test_auxiliary_source_chain_guard_blocks_diagnostic(self):
        fixture = self.fixture()
        fixture.graph['depSetOfFiles'][-1]['directArtifactIds'] = []
        self.assertEqual(fixture.run(), 1)
        self.assertEqual(fixture.builds, [])
        self.assertFalse((fixture.diagnostic / 'diagnostic-complete.json').exists())

    def test_final_copy_failure_never_publishes_completion_marker(self):
        fixture = self.fixture('full')
        fixture.fail_finalization = True
        with self.assertRaisesRegex(OSError, 'final diagnostic contract copy failure'):
            fixture.run()
        self.assertEqual(fixture.builds, [DIAGNOSTIC_NAMES, set(NAMES)])
        # The subset passed collection, but its evidence package is incomplete.
        self.assertTrue((fixture.diagnostic / 'diagnostic-manifest.json').is_file())
        self.assertFalse((fixture.diagnostic / 'artifact-lock.json').exists())
        self.assertFalse((fixture.diagnostic / 'diagnostic-complete.json').exists())
        self.assertFalse((fixture.diagnostic / 'diagnostic-complete.tmp').exists())
        self.assertFalse((fixture.output / 'artifact-manifest.json').exists())

    def test_current_source_guard_still_blocks_both_builds(self):
        fixture = self.fixture()
        (fixture.repo / 'payload/camera.c').write_text('unreviewed bytes\n')
        self.assertEqual(fixture.run(), 1)
        self.assertEqual(fixture.builds, [])
        self.assertNotIn('aquery-15', fixture.events)
        self.assertFalse((fixture.diagnostic / 'diagnostic-manifest.json').exists())
        status = json.loads((fixture.reports / 'r61-targeted-status.json').read_text())
        self.assertIn('Source bytes/SHA mismatch', status['error'])

    def test_full_aquery_source_chain_guard_still_blocks_diagnostic(self):
        fixture = self.fixture()
        # Break an MCA source edge even though the first build needs only two KOs.
        fixture.graph['depSetOfFiles'][0]['directArtifactIds'] = []
        self.assertEqual(fixture.run(), 1)
        self.assertEqual(fixture.builds, [])
        self.assertFalse((fixture.diagnostic / 'diagnostic-manifest.json').exists())
        status = json.loads((fixture.reports / 'r61-targeted-status.json').read_text())
        self.assertIn('source-bound compiler-to-KO', status['error'])

    def test_workflow_upload_requires_validated_diagnostic_marker(self):
        # Check the actual GitHub Actions condition and destination; both the
        # validated outputs and finalized evidence package are required.
        steps = re.split(r'(?m)^      - name: ', WORKFLOW.read_text())[1:]
        uploads = [step for step in steps if 'uses: actions/upload-artifact@' in step
                   and 'r61-targeted-diagnostic' in step]
        self.assertEqual(len(uploads), 1)
        upload = uploads[0]
        condition = re.search(r'(?m)^        if: (.+)$', upload).group(1)
        gate_root = 'kernel_workspace/myron-platform-r1/integration-artifacts/r61-targeted-diagnostic/'
        expected = "${{ !cancelled() && hashFiles('" + gate_root + "diagnostic-manifest.json') != '' && hashFiles('" + gate_root + "diagnostic-complete.json') != '' }}"
        self.assertEqual(condition, expected)
        upload_path = re.search(r'(?m)^          path: (.+)$', upload).group(1)
        self.assertEqual(upload_path, '${{ env.WORKSPACE_DIR }}/integration-artifacts/r61-targeted-diagnostic/')
        self.assertRegex(upload, r'(?m)^          if-no-files-found: error$')


if __name__ == '__main__':
    unittest.main(verbosity=2)
