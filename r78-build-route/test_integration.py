#!/usr/bin/env python3
"""Guard real DDK output selection against expensive late collection failures."""
import copy
import json
from pathlib import Path
import unittest
from resolve_outputs import resolve

HERE=Path(__file__).resolve().parent
class Outputs(unittest.TestCase):
    def setUp(self):
        self.g=json.loads((HERE/'tests/actual-ddk-outputs.json').read_text())
        self.m={'module_name':'myron_buck_thermal','target':'//vendor/qcom/sm8850:canoe_perf/drivers/thermal/myron_buck_thermal','expected_sources':['vendor/qcom/sm8850/drivers/thermal/myron_buck_thermal.c']}
    def test_successful_real_ddk_graph(self):
        row=resolve(self.g,self.m)
        self.assertEqual(row['output'],'bazel-out/aarch64-fastbuild/bin/vendor/qcom/sm8850/canoe_perf/drivers/thermal/myron_buck_thermal/myron_buck_thermal.ko')
        self.assertEqual(row['symvers'],'bazel-out/aarch64-fastbuild/bin/vendor/qcom/sm8850/canoe_perf/drivers/thermal/myron_buck_thermal/canoe_perf/drivers/thermal/myron_buck_thermal_Module.symvers')
    def test_wrong_target_does_not_borrow_dependency_outputs(self):
        self.m['target']='//vendor/qcom/sm8850:not_selected'
        with self.assertRaises(ValueError):resolve(self.g,self.m)
    def test_staging_without_final_copy_is_rejected(self):
        self.g['actions']=[a for a in self.g['actions'] if a['mnemonic']!='KernelModuleCpOutputs']
        with self.assertRaises(ValueError):resolve(self.g,self.m)
    def test_ambiguous_module_symvers_is_rejected(self):
        self.g['artifacts'].append({'id':999999,'execPath':'bazel-out/aarch64-fastbuild/bin/second_Module.symvers'})
        self.g['actions'][0]['outputIds'].append(999999)
        with self.assertRaises(ValueError):resolve(self.g,self.m)
    def test_escaping_output_is_rejected(self):
        self.g['artifacts'].append({'id':999999,'execPath':'../myron_buck_thermal.ko'})
        self.g['actions']=[a for a in self.g['actions'] if a['mnemonic']!='KernelModuleCpOutputs']
        self.g['actions'][0]['outputIds'].append(999999)
        with self.assertRaises(ValueError):resolve(self.g,self.m)

if __name__=='__main__':unittest.main()
