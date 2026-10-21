#!/usr/bin/env python3
"""Negative checks for source confinement and actual BQ compiler-config binding."""
import copy
import json
import shutil
import sys
import tempfile
from pathlib import Path
import unittest
from apply_bq import FULL_BQ, apply, safe
from build_bq import check, verify_effective_bq_config
from test_source import offline_guard_bytes, reconstruct_r84_bq

REPO = Path(__file__).resolve().parent.parent
ROUTE = REPO / 'r85-build-route'
sys.path.insert(0, str(REPO / 'r61-build-route'))
from action_chain import action_chain

TARGET = '//vendor/qcom/sm8850:canoe_perf/drivers/power/supply/mca/mca_hardware_ic/fuelgauge_ic/bq27z561/bq27z561'
TREE = 'bazel-out/aarch64-fastbuild/bin/vendor/qcom/sm8850/canoe_perf_config/out_dir'
SETUP = 'bazel-out/aarch64-fastbuild/bin/vendor/qcom/sm8850/bq_config_setup.sh'
MODULES = [{'module_name': 'bq27z561', 'target': TARGET, 'expected_sources': [FULL_BQ]}]


def graph_fixture():
    return {'targets': [{'id': 1, 'label': '//vendor/qcom/sm8850:canoe_perf_config'},
                        {'id': 2, 'label': TARGET}, {'id': 3, 'label': TARGET + '_config'}],
            'artifacts': [{'id': 10, 'execPath': TREE}, {'id': 11, 'execPath': SETUP}],
            'depSetOfFiles': [{'id': 20, 'directArtifactIds': [10, 11]}],
            'actions': [{'targetId': 1, 'mnemonic': 'DdkConfig', 'outputIds': [10],
                         'arguments': ['write', TREE + '/.config']},
                        {'targetId': 2, 'mnemonic': 'KernelModule', 'inputDepSetIds': [20],
                         'arguments': ['compile', SETUP]},
                        {'targetId': 3, 'mnemonic': 'FileWrite', 'outputIds': [11]}]}


class ConfigGuards(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='r85-build-guards-')
        self.root = Path(self.temporary.name)
        self.config = self.root / TREE / '.config'
        self.config.parent.mkdir(parents=True)
        self.config.write_text('# CONFIG_MYRON_IC_FIRMWARE_PROGRAMMING is not set\n')
        self.graph = graph_fixture()

    def tearDown(self):
        self.temporary.cleanup()

    def test_exact_disabled_config(self):
        result = verify_effective_bq_config(self.root, self.graph, MODULES)
        self.assertEqual(result['status'], 'PASS_ACTUAL_BQ_CONFIG')
        self.assertEqual(result['settings']['CONFIG_MYRON_IC_FIRMWARE_PROGRAMMING'], 'n')

    def test_programming_enabled_rejected(self):
        for value in ('y', 'm'):
            with self.subTest(value=value):
                self.config.write_text('CONFIG_MYRON_IC_FIRMWARE_PROGRAMMING=' + value + '\n')
                with self.assertRaisesRegex(ValueError, 'programming must remain disabled'):
                    verify_effective_bq_config(self.root, self.graph, MODULES)

    def test_unconsumed_config_tree_rejected(self):
        self.graph['depSetOfFiles'][0]['directArtifactIds'] = [11]
        with self.assertRaisesRegex(ValueError, 'does not consume'):
            verify_effective_bq_config(self.root, self.graph, MODULES)

    def test_missing_target_owned_setup_rejected(self):
        self.graph['targets'][2]['label'] = '//other:config'
        with self.assertRaisesRegex(ValueError, 'target config setup'):
            verify_effective_bq_config(self.root, self.graph, MODULES)

    def test_setup_not_used_in_compile_command_rejected(self):
        self.graph['actions'][1]['arguments'] = ['compile']
        with self.assertRaisesRegex(ValueError, 'target config setup'):
            verify_effective_bq_config(self.root, self.graph, MODULES)

    def test_private_config_override_rejected(self):
        self.graph['actions'][2]['mnemonic'] = 'DdkConfig'
        with self.assertRaisesRegex(ValueError, 'per-module'):
            verify_effective_bq_config(self.root, self.graph, MODULES)

    def test_duplicate_config_action_rejected(self):
        self.graph['actions'].append(copy.deepcopy(self.graph['actions'][0]))
        with self.assertRaisesRegex(ValueError, 'one real external'):
            verify_effective_bq_config(self.root, self.graph, MODULES)

    def test_wrong_actual_bq_target_rejected(self):
        self.graph['targets'][1]['label'] = '//other:bq'
        with self.assertRaisesRegex(ValueError, 'Missing real full-BQ'):
            verify_effective_bq_config(self.root, self.graph, MODULES)

    def test_cyclic_compile_depset_rejected(self):
        self.graph['depSetOfFiles'][0]['transitiveDepSetIds'] = [20]
        with self.assertRaisesRegex(ValueError, 'Invalid config depset'):
            verify_effective_bq_config(self.root, self.graph, MODULES)

    def test_missing_materialization_in_action_rejected(self):
        self.graph['actions'][0]['arguments'] = ['write', TREE + '/other-config']
        with self.assertRaisesRegex(ValueError, 'does not materialize'):
            verify_effective_bq_config(self.root, self.graph, MODULES)

    def test_actual_bazel_output_symlink_supported(self):
        actual = self.root / 'actual-output'
        actual.mkdir()
        self.config.write_text('CONFIG_MYRON_IC_FIRMWARE_PROGRAMMING=n\n')
        (self.root / 'bazel-out').rename(actual / 'bazel-out')
        (self.root / 'bazel-out').symlink_to(actual / 'bazel-out', target_is_directory=True)
        self.assertEqual(verify_effective_bq_config(self.root, self.graph, MODULES)['status'],
                         'PASS_ACTUAL_BQ_CONFIG')

    def test_source_escape_and_symlink_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unsafe relative'):
            safe(self.root, '../outside.c')
        inside = self.root / 'inside'
        inside.mkdir()
        (self.root / 'alias').symlink_to(inside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Symlink path'):
            safe(self.root, 'alias/source.c')


class SourceActionGuards(unittest.TestCase):
    def setUp(self):
        self.output = 'bazel-out/reviewed/bq27z561.ko'
        self.graph = {'artifacts': [{'id': 1, 'execPath': FULL_BQ},
                                    {'id': 2, 'execPath': 'bazel-out/reviewed/staging'},
                                    {'id': 3, 'execPath': self.output}],
                      'depSetOfFiles': [{'id': 10, 'directArtifactIds': [1]},
                                       {'id': 11, 'directArtifactIds': [2]}],
                      'actions': [{'mnemonic': 'KernelModule', 'inputDepSetIds': [10], 'outputIds': [2]},
                                  {'mnemonic': 'KernelModuleCpOutputs', 'inputDepSetIds': [11], 'outputIds': [3]}]}

    def test_staging_chain(self):
        self.assertEqual(action_chain(self.graph, [FULL_BQ], self.output)['kind'], 'staging-copy')

    def test_missing_source_rejected(self):
        self.graph['depSetOfFiles'][0]['directArtifactIds'] = []
        with self.assertRaisesRegex(ValueError, 'source-bound'):
            action_chain(self.graph, [FULL_BQ], self.output)

    def test_unrelated_staging_copy_rejected(self):
        self.graph['artifacts'].append({'id': 4, 'execPath': 'bazel-out/unrelated/staging'})
        self.graph['depSetOfFiles'][1]['directArtifactIds'] = [4]
        with self.assertRaisesRegex(ValueError, 'source-bound'):
            action_chain(self.graph, [FULL_BQ], self.output)

    def test_duplicate_output_producer_rejected(self):
        self.graph['actions'].append(copy.deepcopy(self.graph['actions'][1]))
        with self.assertRaisesRegex(ValueError, 'one final KO'):
            action_chain(self.graph, [FULL_BQ], self.output)


@unittest.skipUnless((ROUTE / 'build-contract.json').is_file(), 'Final source/test contract is not frozen yet')
class FrozenOverlayGuards(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='r85-overlay-guards-')
        self.root = Path(self.temporary.name)
        self.route = self.root / 'route'
        shutil.copytree(ROUTE, self.route, ignore=shutil.ignore_patterns('__pycache__'))
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        reconstruct_r84_bq(REPO, self.workspace)
        self.contract_path = self.route / 'SOURCE-CONTRACT.json'
        self.contract = json.loads(self.contract_path.read_text())
        for guard in self.contract['read_only_guards']:
            target = self.workspace / guard['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(offline_guard_bytes(REPO, guard))

    def tearDown(self):
        self.temporary.cleanup()

    def test_final_patch_applies_and_verifies(self):
        apply(self.workspace, self.route)
        self.assertEqual(apply(self.workspace, self.route, verify=True)['status'], 'PASS_R85_EXACT_POSTIMAGES')

    def test_patch_byte_tamper_rejected(self):
        patch = self.route / 'patches/bq-full-safety.patch'
        patch.write_bytes(patch.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'Patch bytes changed'):
            apply(self.workspace, self.route)

    def test_preimage_contract_tamper_rejected(self):
        self.contract['writes'][0]['before']['sha256'] = '0' * 64
        self.contract_path.write_text(json.dumps(self.contract))
        with self.assertRaisesRegex(ValueError, 'Wrong source preimage'):
            apply(self.workspace, self.route)

    def test_header_tamper_rejected(self):
        path = self.workspace / self.contract['header_path']
        path.write_bytes(path.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'Source guard changed'):
            apply(self.workspace, self.route)

    def test_firmware_source_config_tamper_rejected(self):
        path = self.workspace / 'vendor/qcom/sm8850/configs/canoe_perf.bzl'
        before = path.read_bytes()
        self.assertIn(b'"CONFIG_MYRON_IC_FIRMWARE_PROGRAMMING": "n"', before)
        path.write_bytes(before.replace(b'"CONFIG_MYRON_IC_FIRMWARE_PROGRAMMING": "n"',
                                       b'"CONFIG_MYRON_IC_FIRMWARE_PROGRAMMING": "y"'))
        with self.assertRaisesRegex(ValueError, 'Source guard changed'):
            apply(self.workspace, self.route)


@unittest.skipUnless((ROUTE / 'build-contract.json').is_file(), 'Final source/test contract is not frozen yet')
class FrozenClosureGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='r85-closure-guards-')
        cls.repo = Path(cls.temporary.name) / 'repository'
        shutil.copytree(REPO, cls.repo,
                        ignore=shutil.ignore_patterns('.git', '__pycache__'))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.restores = {}

    def tearDown(self):
        for path, data in self.restores.items():
            path.unlink()
            path.write_bytes(data)

    def replace(self, relative, data):
        path = self.repo / relative
        self.restores[path] = path.read_bytes()
        # Replace only this isolated fixture; the reviewed repo is untouched.
        path.unlink()
        path.write_bytes(data)

    def mutate_contract(self, operation):
        path = 'r85-build-route/build-contract.json'
        contract = json.loads((self.repo / path).read_text())
        operation(contract)
        self.replace(path, (json.dumps(contract) + '\n').encode())

    def test_exact_frozen_inputs(self):
        self.assertEqual(len(check(self.repo)[0]['validation_only_modules']), 47)

    def test_runtime_candidate_policy_tamper_rejected(self):
        self.mutate_contract(lambda c: c.update(runtime_candidate_module_names=['bq27z561']))
        with self.assertRaisesRegex(ValueError, 'must stay inactive'):
            check(self.repo)

    def test_activation_policy_tamper_rejected(self):
        self.mutate_contract(lambda c: c.update(activation_allowed=True))
        with self.assertRaisesRegex(ValueError, 'must stay inactive'):
            check(self.repo)

    def test_incomplete_47_module_selection_rejected(self):
        self.mutate_contract(lambda c: c['validation_only_modules'].pop())
        with self.assertRaisesRegex(ValueError, '47-module MCA closure'):
            check(self.repo)

    def test_declared_source_binding_tamper_rejected(self):
        self.mutate_contract(lambda c: c['validation_only_modules'][0].update(expected_sources=['unrelated.c']))
        with self.assertRaisesRegex(ValueError, '47-module MCA closure'):
            check(self.repo)

    def test_retained_r83_mca_source_patch_tamper_rejected(self):
        path = 'r83-build-route/r83-mca-transient-cache.patch'
        self.replace(path, (self.repo / path).read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'Changed locked input'):
            check(self.repo)


if __name__ == '__main__':
    unittest.main()
