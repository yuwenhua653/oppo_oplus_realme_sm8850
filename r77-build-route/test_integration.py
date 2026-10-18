#!/usr/bin/env python3
"""Targeted R77 overlay/configuration and compiled observer metadata regressions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import thermal_inputs as inputs
import apply_thermal as overlay
from build_thermal import verify_observer_metadata,verify_build_wiring
ROOT=Path(__file__).resolve().parents[1]
HERE=Path(__file__).resolve().parent

class IntegrationTests(unittest.TestCase):
    def setUp(self):self.c=json.loads((HERE/'thermal-contract.json').read_text())
    def check(self,c):return inputs.check(ROOT,c,inherited=False)
    def test_frozen_source_layer(self):self.assertEqual(self.check(self.c)['distinct_workspace_destinations'],11)
    def test_unreviewed_source_blocks(self):
        self.c['source_review']='INCOMPLETE'
        with self.assertRaisesRegex(ValueError,'incomplete'):self.check(self.c)
    def test_only_four_targets(self):
        self.c['modules'].append(copy.deepcopy(self.c['modules'][-1]))
        with self.assertRaisesRegex(ValueError,'three frozen'):self.check(self.c)
    def test_actual_source_target_mapping_required(self):
        self.c['modules'][-1]['expected_sources']=[]
        with self.assertRaisesRegex(ValueError,'source/target'):self.check(self.c)
    def test_existing_readonly_bytes_cannot_float(self):
        self.c['unchanged_readonly_KOs']['qti_pmic_glink']['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'KO byte pins'):self.check(self.c)
    def test_runtime_changes_rejected(self):
        self.c['runtime_changes']=['modules.load']
        with self.assertRaisesRegex(ValueError,'compile-only'):self.check(self.c)
    def test_exact_four_overlay_operations(self):
        self.c['writes'].append(copy.deepcopy(self.c['writes'][0]))
        with self.assertRaisesRegex(ValueError,'four R77'):self.check(self.c)
    def test_append_cannot_use_unpinned_parent(self):
        row=next(r for r in self.c['writes'] if r['mode']=='append_parent');row['before_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'parent append'):self.check(self.c)
    def test_new_source_cannot_replace_an_old_driver(self):
        row=next(r for r in self.c['writes'] if r['mode']=='replace');row['before_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'new independent'):self.check(self.c)
    def test_build_fragment_mapping_and_default(self):
        fragments=[(HERE/'fragments'/n).read_text() for n in ('Kconfig','modules.bzl','canoe_perf.bzl')]
        inputs.check_fragments(*fragments)
        for i,old,new in [(0,'default n','default y'),(1,inputs.STEM+'.c','drivers/other.c'),(2,'= "m"','= "y"')]:
            changed=list(fragments);changed[i]=changed[i].replace(old,new)
            with self.assertRaises(ValueError):inputs.check_fragments(*changed)
    def populate_parent_state(self,workspace):
        _,checker,parent,prior=inputs.parents(ROOT)
        for row in prior['writes']+parent['writes']:
            p=workspace/row['destination'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(checker.overlay_bytes(ROOT,row))
    def test_parent_state_to_final_idempotent_then_verify(self):
        with tempfile.TemporaryDirectory() as td:
            w=Path(td);self.populate_parent_state(w)
            with patch.object(overlay.subprocess,'check_output',side_effect=list(self.c['git_heads'].values())*4):
                with self.assertRaisesRegex(ValueError,'not applied'):overlay.apply(w,ROOT,self.c,True)
                report=overlay.apply(w,ROOT,self.c);self.assertEqual(sum(r['changed'] for r in report['writes']),4)
                self.assertTrue(all(not r['changed'] for r in overlay.apply(w,ROOT,self.c)['writes']))
                self.assertEqual(overlay.apply(w,ROOT,self.c,True)['mode'],'verify')
    def test_late_new_source_conflict_blocks_all_config_writes(self):
        with tempfile.TemporaryDirectory() as td:
            w=Path(td);self.populate_parent_state(w);old={n:(w/n).read_bytes() for n in inputs.APPENDS}
            new=w/(inputs.VENDOR+inputs.STEM+'.c');new.parent.mkdir(parents=True,exist_ok=True);new.write_bytes(b'user existing source')
            with patch.object(overlay.subprocess,'check_output',side_effect=list(self.c['git_heads'].values())):
                with self.assertRaisesRegex(ValueError,'Unexpected layered preimage'):overlay.apply(w,ROOT,self.c)
            self.assertTrue(all((w/n).read_bytes()==data for n,data in old.items()))
    def test_unknown_config_append_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            w=Path(td);self.populate_parent_state(w);p=w/next(iter(inputs.APPENDS));p.write_bytes(p.read_bytes()+b'# local edit\n')
            before=p.read_bytes()
            with patch.object(overlay.subprocess,'check_output',side_effect=list(self.c['git_heads'].values())):
                with self.assertRaisesRegex(ValueError,'Unexpected layered preimage'):overlay.apply(w,ROOT,self.c)
            self.assertEqual(p.read_bytes(),before)
    def test_observer_metadata_scope(self):
        good={'name':'myron_buck_thermal','depends':[],'exports':[], 'imports':['sysfs_create_group'], 'info':{'parmtype':['enable_observer:bool']}}
        self.assertFalse(verify_observer_metadata(good)['runtime_load_approved'])
        for key,value in [('depends',['mca_log']),('exports',['private_export']),('imports',['mca_vote'])]:
            bad=copy.deepcopy(good);bad[key]=value
            with self.assertRaises(ValueError):verify_observer_metadata(bad)
        bad=copy.deepcopy(good);bad['info']['parmtype'].append('enable_observer:bool')
        with self.assertRaises(ValueError):verify_observer_metadata(bad)
    def test_real_ddk_generator_required_and_old_targets_omitted(self):
        target=self.c['modules'][-1]
        graph={'targets':[{'id':1,'label':target['target']+'_makefiles'},{'id':2,'label':'//old:mca'}],
               'actions':[{'targetId':1,'mnemonic':'DdkMakefiles','arguments':['gen_makefiles','--produce-top-level-makefile',
                   '--kernel-module-out','myron_buck_thermal.ko','--package','vendor/qcom/sm8850']}]}
        verify_build_wiring(graph,target,['//old:mca'])
        bad=copy.deepcopy(graph);bad['actions'][0]['arguments'].remove('--produce-top-level-makefile')
        with self.assertRaises(ValueError):verify_build_wiring(bad,target,['//old:mca'])
        graph['actions'].append({'targetId':2,'mnemonic':'KernelModule'})
        with self.assertRaises(ValueError):verify_build_wiring(graph,target,['//old:mca'])

if __name__=='__main__':unittest.main()
