#!/usr/bin/env python3
"""Negative integration tests: scope, preimages, source pins and mutation order."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import check_charge_inputs as check
import apply_charge as apply
from build_charge import verify_pair_metadata, verify_gauge_metadata

HERE = Path(__file__).resolve().parent
REPO = HERE.parent


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads((HERE / 'charge-contract.json').read_text())

    def test_frozen_overlay_inputs(self):
        self.assertEqual(check.check_overlay(REPO, self.contract)['modules'], ['myron_bq_readonly', 'myron_mca_readonly', 'qti_pmic_glink'])

    def test_closed_scope_rejects_extra_module(self):
        c = copy.deepcopy(self.contract)
        c['modules'].append(copy.deepcopy(c['modules'][0]))
        with self.assertRaisesRegex(ValueError, 'Only QTI'):
            check.check_overlay(REPO, c)

    def test_scope_rejects_missing_gauge(self):
        c = copy.deepcopy(self.contract)
        c['modules'] = [row for row in c['modules'] if row['module_name'] != 'myron_bq_readonly']
        with self.assertRaisesRegex(ValueError, 'Only QTI'):
            check.check_overlay(REPO, c)

    def test_gauge_preimage_cannot_float(self):
        c = copy.deepcopy(self.contract)
        row = next(row for row in c['writes'] if row['destination'].endswith('/myron_bq_readonly.c'))
        row['before_sha256'] = None
        with self.assertRaisesRegex(ValueError, 'gauge preimage'):
            check.check_overlay(REPO, c)

    def test_target_source_set_cannot_omit_header(self):
        c = copy.deepcopy(self.contract)
        c['modules'][0]['expected_sources'] = c['modules'][0]['expected_sources'][:1]
        with self.assertRaisesRegex(ValueError, 'Unpinned target sources'):
            check.check_overlay(REPO, c)

    def test_target_redirect_rejected(self):
        c = copy.deepcopy(self.contract)
        c['modules'][0]['stem'] = 'drivers/soc/qcom/other'
        with self.assertRaisesRegex(ValueError, 'Module stem'):
            check.check_overlay(REPO, c)

    def test_core_metadata_cannot_be_removed(self):
        c = copy.deepcopy(self.contract)
        c['core_targets'] = []
        with self.assertRaisesRegex(ValueError, 'core metadata'):
            check.check_overlay(REPO, c)

    def test_source_revision_cannot_float(self):
        c = copy.deepcopy(self.contract)
        c['git_heads']['common'] = 'main'
        with self.assertRaisesRegex(ValueError, 'HEAD pins'):
            check.check_overlay(REPO, c)

    def test_duplicate_write_rejected(self):
        c = copy.deepcopy(self.contract)
        c['writes'].append(copy.deepcopy(c['writes'][0]))
        with self.assertRaisesRegex(ValueError, 'seven destinations'):
            check.check_overlay(REPO, c)

    def test_placeholder_review_rejected(self):
        c = copy.deepcopy(self.contract)
        c['source_review'] = 'INCOMPLETE'
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            check.check_overlay(REPO, c)

    def test_disconnected_source_rejected(self):
        c = copy.deepcopy(self.contract)
        c['modules'][0]['expected_sources'] = ['vendor/unrelated.c']
        with self.assertRaisesRegex(ValueError, 'Unpinned target sources'):
            check.check_overlay(REPO, c)

    def test_source_tampering_is_rejected_before_any_write(self):
        c = copy.deepcopy(self.contract)
        c['locked_files'][0]['sha256'] = '0' * 64
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, 'Input bytes/SHA mismatch'):
                apply.apply(Path(td), REPO, c)
            self.assertEqual(list(Path(td).rglob('*')), [])

    def test_unexpected_late_preimage_causes_no_earlier_write(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rows = []
            for name in ['first.c', 'last.c']:
                data = b'old-' + name.encode()
                (root / name).write_bytes(data)
                rows.append({'destination': name, 'before_sha256': check.sha(data),
                             'after_sha256': check.sha(b'new-' + name.encode())})
            (root / 'last.c').write_bytes(b'conflicting user edit')
            c = {'git_heads': {}, 'writes': rows}
            with patch.object(apply, 'check_overlay'), patch.object(apply, 'overlay_bytes',
                       side_effect=lambda repo, row: b'new-' + row['destination'].encode()):
                with self.assertRaisesRegex(ValueError, 'Unexpected preimage'):
                    apply.apply(root, REPO, c)
            self.assertEqual((root / 'first.c').read_bytes(), b'old-first.c')
            self.assertEqual((root / 'last.c').read_bytes(), b'conflicting user edit')

    def test_apply_is_idempotent_and_verify_requires_postimage(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'old.c').write_bytes(b'old')
            c = {'git_heads': {}, 'writes': [
                {'destination': 'old.c', 'before_sha256': check.sha(b'old'), 'after_sha256': check.sha(b'new')},
                {'destination': 'nested/new.c', 'before_sha256': None, 'after_sha256': check.sha(b'new')}]}
            with patch.object(apply, 'check_overlay'), patch.object(apply, 'overlay_bytes', return_value=b'new'):
                with self.assertRaisesRegex(ValueError, 'not applied'):
                    apply.apply(root, REPO, c, verify=True)
                self.assertTrue(all(r['changed'] for r in apply.apply(root, REPO, c)['writes']))
                self.assertTrue(all(not r['changed'] for r in apply.apply(root, REPO, c)['writes']))
                self.assertTrue(all(not r['changed'] for r in apply.apply(root, REPO, c, verify=True)['writes']))

    def test_parent_directory_symlink_cannot_escape(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            root = Path(a)
            (root / 'redirect').symlink_to(b, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'Redirected path'):
                check.safe(root, 'redirect/file.c', exists=False)

    def test_append_requires_exact_reference(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'before').write_bytes(b'before')
            (root / 'fragment').write_bytes(b'after')
            row = {'mode': 'append', 'source': 'fragment', 'preimage': 'before', 'before_sha256': check.sha(b'wrong')}
            with self.assertRaisesRegex(ValueError, 'Append preimage'):
                check.overlay_bytes(root, row)

    def test_compiled_pair_requires_new_import_and_matching_crc(self):
        name = 'pmic_glink_unregister_client_sync'
        client = {'name': 'myron_mca_readonly', 'imports': {name}, 'versions': {name: 123}, 'depends': ['qti_pmic_glink']}
        transport = {'name': 'qti_pmic_glink', 'exports': {name}, 'export_crcs': {name: 123}}
        self.assertEqual(verify_pair_metadata(client, transport)['status'], 'PASS_COMPILED_PAIR_ONLY')
        transport['export_crcs'][name] = 456
        with self.assertRaisesRegex(ValueError, 'CRC mismatch'):
            verify_pair_metadata(client, transport)
        transport['export_crcs'][name] = 123
        client['imports'].add('pmic_glink_unregister_client')
        with self.assertRaisesRegex(ValueError, 'fallback'):
            verify_pair_metadata(client, transport)
        client['imports'] = set()
        with self.assertRaisesRegex(ValueError, 'new-backend import'):
            verify_pair_metadata(client, transport)

    def test_compiled_gauge_cannot_gain_mca_dependency(self):
        gauge = {'name': 'myron_bq_readonly', 'depends': [], 'imports': {'power_supply_get_by_name'}}
        self.assertEqual(verify_gauge_metadata(gauge)['status'], 'PASS_COMPILED_GAUGE_ONLY')
        gauge['imports'].add('pmic_glink_write')
        with self.assertRaisesRegex(ValueError, 'core power_supply'):
            verify_gauge_metadata(gauge)
        gauge['imports'] = set()
        gauge['depends'] = ['qti_pmic_glink']
        with self.assertRaisesRegex(ValueError, 'unexpected module dependency'):
            verify_gauge_metadata(gauge)

    def test_gauge_host_suite_cannot_be_omitted(self):
        c = copy.deepcopy(self.contract)
        c['host_tests'] = [row for row in c['host_tests'] if row['name'] != 'gauge']
        with self.assertRaisesRegex(ValueError, 'Three production'):
            check.check_overlay(REPO, c)

    def test_header_api_ignores_comments_but_detects_signature_change(self):
        a = b'/* doc */ int f(void *p);\n'
        b = b'// new docs\nint f( void * p );\n'
        self.assertEqual(check.header_tokens(a), check.header_tokens(b))
        self.assertNotEqual(check.header_tokens(a), check.header_tokens(b.replace(b'int f', b'void f')))


if __name__ == '__main__':
    unittest.main()
