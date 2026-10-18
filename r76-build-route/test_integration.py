#!/usr/bin/env python3
"""Negative scope and transaction checks for the new three-source layer."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import foundation_inputs as inputs
import apply_foundation as overlay
from build_foundation import verify_foundation_metadata
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
checker,parent_apply=inputs.parent_modules(ROOT)

class IntegrationTests(unittest.TestCase):
    def setUp(self):self.c=json.loads((HERE/'foundation-contract.json').read_text())
    def check(self,c):return inputs.check(ROOT,c,inherited=False)
    def test_valid_frozen_layer(self):self.assertEqual(self.check(self.c)['total_overlay_writes'],10)
    def test_no_runtime_changes(self):
        self.c['runtime_changes']=['modules.load']
        with self.assertRaisesRegex(ValueError,'compile-only'):self.check(self.c)
    def test_source_review_required(self):
        self.c['source_review']='INCOMPLETE'
        with self.assertRaisesRegex(ValueError,'incomplete'):self.check(self.c)
    def test_parent_cannot_float(self):
        self.c['parent_contract_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'parent identity'):self.check(self.c)
    def test_source_head_cannot_float(self):
        self.c['base_commit']='main'
        with self.assertRaisesRegex(ValueError,'remote base'):self.check(self.c)
    def test_exact_six_targets(self):
        self.c['modules']=self.c['modules'][:3]
        with self.assertRaisesRegex(ValueError,'six collected'):self.check(self.c)
    def test_no_extra_target(self):
        self.c['modules'].append(copy.deepcopy(self.c['modules'][-1]))
        with self.assertRaisesRegex(ValueError,'six collected'):self.check(self.c)
    def test_modified_source_is_a_build_input(self):
        self.c['modules'][-1]['expected_sources']=[]
        with self.assertRaisesRegex(ValueError,'disconnected'):self.check(self.c)
    def test_target_cannot_redirect(self):
        self.c['modules'][-1]['target']='//elsewhere:unrelated'
        with self.assertRaisesRegex(ValueError,'disconnected'):self.check(self.c)
    def test_no_extra_write(self):
        self.c['writes'].append(copy.deepcopy(self.c['writes'][-1]))
        with self.assertRaisesRegex(ValueError,'three exact'):self.check(self.c)
    def test_preimage_cannot_float(self):
        self.c['writes'][-1]['before_sha256']=None
        with self.assertRaisesRegex(ValueError,'pre/postimage'):self.check(self.c)
    def test_transport_postimage_cannot_drift(self):
        self.c['writes'][0]['after_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'pre/postimage'):self.check(self.c)
    def test_no_runtime_closure_claim(self):
        self.c['dependency_policy']='runtime_approved'
        with self.assertRaisesRegex(ValueError,'collection claim'):self.check(self.c)
    def test_bad_source_lock_prevents_any_mutation(self):
        self.c['locked_files'][-1]['sha256']='0'*64
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):overlay.apply(Path(td),ROOT,self.c)
            self.assertEqual(list(Path(td).rglob('*')),[])
    def test_late_bad_preimage_prevents_prior_R75_write(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);first=root/'parent.c';first.write_bytes(b'parent-old')
            for row in self.c['writes']:
                p=root/row['destination'];p.parent.mkdir(parents=True,exist_ok=True)
                p.write_bytes((ROOT/row['source']).read_bytes())
            (root/self.c['writes'][-1]['destination']).write_bytes(b'conflicting edit')
            with patch.object(overlay,'check'),patch.object(parent_apply,'plan',return_value=[(first,b'parent-new',True)]):
                with self.assertRaisesRegex(ValueError,'Unexpected R76 preimage'):overlay.apply(root,ROOT,self.c)
            self.assertEqual(first.read_bytes(),b'parent-old')
    def test_exact_layer_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for row in self.c['writes']:
                p=root/row['destination'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/row['source']).read_bytes())
            with patch.object(overlay,'check'),patch.object(parent_apply,'plan',return_value=[]):
                self.assertTrue(all(not row['changed'] for row in overlay.apply(root,ROOT,self.c)['writes']))
                self.assertEqual(overlay.apply(root,ROOT,self.c,True)['mode'],'verify')
    def test_compiled_transport_pair_crc(self):
        symbols={'mca_adsp_glink_write_prop':123,'mca_adsp_glink_read_prop':456}
        pair={'mca_adsp_glink':{'exports':list(symbols),'export_crcs':symbols},
              'mca_qcom_subpmic_proxy':{'imports':list(symbols),'versions':dict(symbols)}}
        self.assertFalse(verify_foundation_metadata(pair)['runtime_load_approved'])
        pair['mca_qcom_subpmic_proxy']['versions']['mca_adsp_glink_write_prop']=0
        with self.assertRaisesRegex(ValueError,'CRC mismatch'):verify_foundation_metadata(pair)

if __name__=='__main__':unittest.main()
