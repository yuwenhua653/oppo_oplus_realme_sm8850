#!/usr/bin/env python3
"""Exercise exact-source application, including all-or-nothing preflight."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from apply_repairs import apply
from r79_inputs import check, safe, sha

REPO = Path(__file__).resolve().parents[1]

class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads((REPO / 'r79-build-route/repair-contract.json').read_text())

    def fixture(self, root):
        for row in self.contract['writes']:
            if row['before_sha256'] is not None:
                data = safe(REPO, row['preimage_source']).read_bytes()
                self.assertEqual(sha(data), row['before_sha256'])
                p = root / row['destination']
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)

    def test_frozen_parent_and_inputs(self):
        self.assertEqual(check(REPO, self.contract)['status'], 'PASS')

    def test_camera_cannot_drop_out_of_explicit_build(self):
        c = copy.deepcopy(self.contract)
        c['modules'] = [m for m in c['modules'] if m['module_name'] != 'camera']
        c['selected_module_names'].remove('camera')
        with self.assertRaisesRegex(ValueError, 'Required repair target missing'):
            check(REPO, c)

    def test_charging_patch_cannot_be_omitted_from_build(self):
        c = copy.deepcopy(self.contract)
        c['modules'] = [m for m in c['modules'] if m['module_name'] != 'mca_qcom_subpmic_proxy']
        c['selected_module_names'].remove('mca_qcom_subpmic_proxy')
        with self.assertRaisesRegex(ValueError, 'Required repair target missing'):
            check(REPO, c)

    def test_wrong_postimage_rejected(self):
        c = copy.deepcopy(self.contract)
        c['writes'][0]['after_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Wrong postimage'):
            check(REPO, c)

    def test_apply_idempotent_and_verify(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root)
            apply(root, REPO, self.contract)
            apply(root, REPO, self.contract)
            apply(root, REPO, self.contract, verify=True)
            for row in self.contract['writes']:
                self.assertEqual(sha((root / row['destination']).read_bytes()), row['after_sha256'])

    def test_late_bad_preimage_leaves_all_earlier_files_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root)
            last = root / self.contract['writes'][-1]['destination']
            last.parent.mkdir(parents=True, exist_ok=True)
            last.write_bytes(b'wrong source revision\n')
            before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with self.assertRaisesRegex(ValueError, 'Unexpected R79 preimage'):
                apply(root, REPO, self.contract)
            after = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            self.assertEqual(before, after)

    def test_redirected_destination_rejected(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            root = Path(d)
            self.fixture(root)
            p = root / self.contract['writes'][0]['destination']
            p.parent.mkdir(parents=True, exist_ok=True)
            p.unlink(missing_ok=True)
            p.symlink_to(Path(outside) / 'source.c')
            with self.assertRaisesRegex(ValueError, 'Redirected path'):
                apply(root, REPO, self.contract)

if __name__ == '__main__':
    unittest.main()
