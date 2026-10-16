#!/usr/bin/env python3
"""Exercise the real compile-only builder and collector with 49 reviewed KOs.

External compiler/preparation commands and ELF decoding use fixtures. Source
locks, action guards, explicit targets, file copies, hashes, module inventory,
failure status and upload completion markers execute production code.
"""
import json
from pathlib import Path
import re
import tempfile
import unittest

from test_diagnostic_preservation import (
    AUXILIARY_NAMES, BIN, BuildFixture, DIAGNOSTIC_AUXILIARY,
    DIAGNOSTIC_NAMES, NAMES, ROUTE, WORKFLOW, load_implementation, sha,
    write_json,
)


REVIEW = json.loads((ROUTE / 'runtime-closure-scope.json').read_text())
CLOSURE_NAMES = [row['module_name'] for row in REVIEW['runtime_closure_modules']]
ALL_NAMES = NAMES + AUXILIARY_NAMES + CLOSURE_NAMES


class ClosureFixture(BuildFixture):
    def __init__(self, base, implementation, failure=None, missing=None):
        self.closure = []
        self.closure_builds = []
        self.missing = missing
        super().__init__(base, implementation, failure)
        writes = json.loads((self.repo / 'write-lock.json').read_text())
        for name in CLOSURE_NAMES:
            source = 'vendor/fixture/' + name + '.c'
            data = ('/* reviewed runtime dependency: ' + name + ' */\n').encode()
            self.write_workspace(source, data)
            postimage = 'payload/' + name + '.c'
            self.lock_file(postimage, data)
            self.integrated.append({'path': source, 'sha256': sha(data)})
            writes['writes'].append({'source': postimage, 'destination': source,
                                     'before_sha256': None, 'preimage': None,
                                     'after_sha256': sha(data)})
            self.closure.append({'module_name': name, 'target': '//vendor/fixture:' + name,
                'output': BIN + 'vendor/fixture/' + name + '/' + name + '.ko',
                'symvers': BIN + 'vendor/fixture/' + name + '/Module.symvers',
                'expected_sources': [source]})
        self.relock('write-lock.json', writes)
        scope = json.loads((self.repo / 'reviewed-scope.json').read_text())
        scope['reviewed_runtime_closure_module_names'] = CLOSURE_NAMES
        self.relock('reviewed-scope.json', scope)
        review = {'frozen': True, 'runtime_closure_modules': self.closure,
                  'workspace_files': self.integrated}
        self.lock_file('closure-review.json', json.dumps(review).encode())
        self.contract.update(runtime_closure_modules=self.closure,
                             runtime_closure_manifest='closure-review.json')
        write_json(self.contract_path, self.contract)
        self.graph = self.make_graph()

    def relock(self, name, value):
        data = json.dumps(value).encode()
        (self.repo / name).write_bytes(data)
        row = next(row for row in self.locked if row['path'] == name)
        row.update(sha256=sha(data), bytes=len(data))

    def make_graph(self):
        graph = super().make_graph()
        for row in self.closure:
            source_id, ko_id, symvers_id = [str(len(graph['artifacts']) + i) for i in (1, 2, 3)]
            graph['artifacts'].extend([
                {'id': source_id, 'execPath': row['expected_sources'][0]},
                {'id': ko_id, 'execPath': row['output']},
                {'id': symvers_id, 'execPath': row['symvers']},
            ])
            dep_id = str(len(graph['depSetOfFiles']) + 1)
            graph['depSetOfFiles'].append({'id': dep_id, 'directArtifactIds': [source_id]})
            graph['actions'].append({'mnemonic': 'KernelModule',
                'actionKey': 'closure-' + row['module_name'],
                'inputDepSetIds': [dep_id], 'outputIds': [ko_id, symvers_id]})
        return graph

    def assert_analysis_complete(self):
        actions = list(self.reports.glob('r61-targeted-action-*.json'))
        assert len(actions) == len(ALL_NAMES), 'Build started before all 49 source action guards'
        assert all(json.loads(path.read_text())['status'] == 'PASS' for path in actions)
        assert 'aquery-reviewed' in self.events

    def logged(self, argv, root, log):
        self.requested_closure = [row for row in self.closure if row['target'] in argv]
        if argv[:2] == ['fixture-bazel', 'build']:
            self.closure_builds.append({row['module_name'] for row in self.requested_closure})
        super().logged(argv, root, log)
        full = argv[:2] == ['fixture-bazel', 'build'] and len(self.selected(argv)) == len(NAMES)
        if full and self.missing:
            row = next(row for row in self.modules + self.auxiliary + self.closure
                       if row['module_name'] == self.missing)
            (self.workspace / row['output']).unlink()
        if full and self.failure == 'wrong_closure_elf_name':
            self.write_workspace(self.closure[0]['output'], b'ELF-FIXTURE:wrong_module_name')

    def produce(self, modules, full, selected_auxiliary):
        super().produce(modules, full, selected_auxiliary)
        for row in self.requested_closure:
            self.write_workspace(row['symvers'], b'0x12345678 fixture_export\n')
            if self.failure != 'closure_symvers_and_staging_only':
                self.write_workspace(row['output'], ('ELF-FIXTURE:' + row['module_name']).encode())
            # A staging object is not the declared final CopyOutputs KO.
            staging = str(Path(row['output']).parent / 'staging' / (row['module_name'] + '.ko'))
            self.write_workspace(staging, ('ELF-FIXTURE:' + row['module_name']).encode())

    def subprocess_run(self, argv, **kwargs):
        result = super().subprocess_run(argv, **kwargs)
        if argv[1] == 'aquery':
            assert all(row['target'] in ' '.join(argv) for row in self.closure)
        if argv[1] == 'cquery' and len(self.selected(argv)) == len(NAMES):
            additions = [row[key] for row in self.closure for key in ('output', 'symvers')]
            additions += [str(Path(row['output']).parent / 'staging' / (row['module_name'] + '.ko'))
                          for row in self.closure]
            result.stdout += '\n'.join(additions) + '\n'
        return result


class RuntimeClosureCollectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.impl = load_implementation()
        assert len(CLOSURE_NAMES) == 30 and len(set(ALL_NAMES)) == 49

    def run_fixture(self, failure=None, missing=None):
        temp = tempfile.TemporaryDirectory(prefix='r64-closure-main-')
        self.addCleanup(temp.cleanup)
        return ClosureFixture(Path(temp.name), self.impl, failure, missing)

    def assert_preserved_subset(self, fixture):
        completion = json.loads((fixture.diagnostic / 'diagnostic-complete.json').read_text())
        self.assertTrue(completion['full_build_not_passed'])
        inv = json.loads((fixture.diagnostic / 'module-inventory.json').read_text())
        self.assertEqual(set(inv['required_module_names']), DIAGNOSTIC_NAMES | DIAGNOSTIC_AUXILIARY)
        self.assertEqual(inv['module_count'], 4)
        self.assertEqual(len(list(fixture.diagnostic.rglob('*.ko'))), 4)
        self.assertFalse((fixture.output / 'candidate-complete.json').exists())
        self.assertFalse(json.loads((fixture.reports / 'r61-targeted-status.json').read_text())['success'])

    def test_all_49_required_kos_are_explicitly_built_and_collected(self):
        fixture = self.run_fixture()
        self.assertEqual(fixture.run(), 0)
        self.assertEqual(fixture.closure_builds, [set(), set(CLOSURE_NAMES)])
        inv = json.loads((fixture.output / 'module-inventory.json').read_text())
        self.assertEqual(inv['required_module_names'], sorted(ALL_NAMES))
        self.assertEqual(inv['module_count'], 49)
        self.assertTrue(inv['compiled_collection_complete'])
        self.assertEqual(len(list(fixture.output.rglob('*.ko'))), 49)
        self.assertFalse(any('/staging/' in row['file'] for row in inv['modules']))
        self.assertFalse(inv['flashable'])
        self.assertEqual(inv['runtime_abi_compatible'], 'NOT_YET_VALIDATED')
        marker = json.loads((fixture.output / 'candidate-complete.json').read_text())
        self.assertEqual(marker['required_module_count'], 49)
        self.assertEqual(marker['module_inventory_sha256'], sha((fixture.output / 'module-inventory.json').read_bytes()))
        self.assertEqual(marker['artifact_lock_sha256'], sha((fixture.output / 'artifact-lock.json').read_bytes()))
        self.assertEqual(len(list(fixture.diagnostic.rglob('*.ko'))), 4)

    def test_symvers_and_staging_do_not_substitute_final_kos(self):
        fixture = self.run_fixture('closure_symvers_and_staging_only')
        self.assertEqual(fixture.run(), 1)
        self.assert_preserved_subset(fixture)
        self.assertFalse((fixture.output / 'module-inventory.json').exists())

    def test_each_of_49_required_kos_missing_refuses_completion(self):
        for name in ALL_NAMES:
            with self.subTest(module=name), tempfile.TemporaryDirectory(prefix='r64-missing-ko-') as temp:
                fixture = ClosureFixture(Path(temp), self.impl, missing=name)
                self.assertEqual(fixture.run(), 1)
                self.assert_preserved_subset(fixture)
                self.assertFalse((fixture.output / 'module-inventory.json').exists())

    def test_wrong_closure_elf_name_refuses_completion(self):
        fixture = self.run_fixture('wrong_closure_elf_name')
        self.assertEqual(fixture.run(), 1)
        self.assert_preserved_subset(fixture)
        self.assertFalse((fixture.output / 'module-inventory.json').exists())

    def test_later_build_failure_preserves_four_module_diagnostic(self):
        fixture = self.run_fixture('full')
        self.assertEqual(fixture.run(), 1)
        self.assert_preserved_subset(fixture)

    def test_frozen_closure_source_guard_blocks_both_builds(self):
        fixture = self.run_fixture()
        fixture.contract['runtime_closure_modules'][0]['target'] += '_unreviewed'
        write_json(fixture.contract_path, fixture.contract)
        self.assertEqual(fixture.run(), 1)
        self.assertEqual(fixture.builds, [])
        self.assertFalse((fixture.diagnostic / 'diagnostic-complete.json').exists())

    def test_full_upload_requires_finalized_completion_marker(self):
        steps = re.split(r'(?m)^      - name: ', WORKFLOW.read_text())[1:]
        uploads = [s for s in steps if 'uses: actions/upload-artifact@' in s
                   and 'r61-targeted-battery/' in s]
        self.assertEqual(len(uploads), 1)
        condition = re.search(r'(?m)^        if: (.+)$', uploads[0]).group(1)
        self.assertIn("candidate-complete.json') != ''", condition)
        self.assertIn("artifact-manifest.json') != ''", condition)


if __name__ == '__main__':
    unittest.main(verbosity=2)
