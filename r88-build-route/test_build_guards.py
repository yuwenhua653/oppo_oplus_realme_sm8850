#!/usr/bin/env python3
"""Guard exact R87 ancestry, FG policy overlays and private header inputs."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from apply_fg_policy import FG_HEADER, FULL_BQ, GLINK, HEADER, PREFIX, SOC, STORAGE, STRATEGY, USB, apply, safe
from build_fg_policy import check
from test_source import reconstruct_inputs

REPO = Path(__file__).resolve().parent.parent
ROUTE = REPO / 'r88-build-route'
sys.path.insert(0, str(REPO / 'r61-build-route'))
from action_chain import action_chain


class CompositeActionGuards(unittest.TestCase):
    def setUp(self):
        self.source = PREFIX + 'drivers/power/supply/mca/mca_strategy/strategy_fg/mca_strategy_fg.c'
        self.output = 'bazel-out/reviewed/mca_strategy_fg_comp.ko'
        self.graph = {'artifacts': [{'id': 1, 'execPath': self.source}, {'id': 2, 'execPath': FG_HEADER},
                                    {'id': 3, 'execPath': 'bazel-out/reviewed/staging'},
                                    {'id': 4, 'execPath': self.output}, {'id': 5, 'execPath': SOC}],
                      'depSetOfFiles': [{'id': 10, 'directArtifactIds': [1, 2, 5]},
                                       {'id': 11, 'directArtifactIds': [3]}],
                      'actions': [{'mnemonic': 'KernelModule', 'inputDepSetIds': [10], 'outputIds': [3]},
                                  {'mnemonic': 'KernelModuleCpOutputs', 'inputDepSetIds': [11], 'outputIds': [4]}]}

    def test_repaired_sources_and_header_feed_the_same_fg_action(self):
        self.assertEqual(action_chain(self.graph, [self.source, SOC, FG_HEADER], self.output)['kind'], 'staging-copy')

    def test_missing_private_header_rejected(self):
        self.graph['depSetOfFiles'][0]['directArtifactIds'] = [1, 5]
        with self.assertRaisesRegex(ValueError, 'source-bound'):
            action_chain(self.graph, [self.source, SOC, FG_HEADER], self.output)

    def test_missing_soc_source_rejected(self):
        self.graph['depSetOfFiles'][0]['directArtifactIds'] = [1, 2]
        with self.assertRaisesRegex(ValueError, 'source-bound'):
            action_chain(self.graph, [self.source, SOC, FG_HEADER], self.output)


class ExactOverlayGuards(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='r88-guards-')
        self.root = Path(self.temporary.name)
        self.route = self.root / 'route'
        shutil.copytree(ROUTE, self.route, ignore=shutil.ignore_patterns('__pycache__'))
        self.contract_path = self.route / 'SOURCE-CONTRACT.json'
        self.contract = json.loads(self.contract_path.read_text())
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        reconstruct_inputs(REPO, self.workspace, self.contract)

    def tearDown(self):
        self.temporary.cleanup()

    def test_exact_patch_applies_and_verifies(self):
        apply(self.workspace, self.route)
        self.assertEqual(apply(self.workspace, self.route, verify=True)['status'], 'PASS_R88_EXACT_POSTIMAGES')

    def test_patch_tamper_rejected(self):
        path = self.route / 'patches/fg-policy-separation.patch'
        path.write_bytes(path.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'Patch bytes changed'):
            apply(self.workspace, self.route)

    def test_each_preimage_is_required(self):
        for path in (STRATEGY, FG_HEADER, SOC):
            with self.subTest(path=path):
                target = safe(self.workspace, path)
                old = target.read_bytes()
                target.write_bytes(old + b'\n')
                with self.assertRaisesRegex(ValueError, 'Wrong source preimage'):
                    apply(self.workspace, self.route)
                target.write_bytes(old)

    def test_extra_write_rejected(self):
        self.contract['writes'].append(copy.deepcopy(self.contract['writes'][0]))
        self.contract_path.write_text(json.dumps(self.contract))
        with self.assertRaisesRegex(ValueError, 'Only reviewed'):
            apply(self.workspace, self.route)

    def test_retained_guard_sources_cannot_change(self):
        for path in (FULL_BQ, HEADER, STORAGE, USB, GLINK):
            with self.subTest(path=path):
                target = safe(self.workspace, path)
                old = target.read_bytes()
                target.write_bytes(old + b'\n')
                with self.assertRaisesRegex(ValueError, 'Source guard changed'):
                    apply(self.workspace, self.route)
                target.write_bytes(old)

    def test_firmware_programming_config_tamper_rejected(self):
        target = self.workspace / PREFIX / 'configs/canoe_perf.bzl'
        target.write_bytes(target.read_bytes().replace(b'"CONFIG_MYRON_IC_FIRMWARE_PROGRAMMING": "n"',
                                                     b'"CONFIG_MYRON_IC_FIRMWARE_PROGRAMMING": "y"'))
        with self.assertRaisesRegex(ValueError, 'Source guard changed'):
            apply(self.workspace, self.route)

    def test_overlay_cannot_be_applied_twice(self):
        apply(self.workspace, self.route)
        with self.assertRaisesRegex(ValueError, 'Wrong source preimage'):
            apply(self.workspace, self.route)

    def test_source_symlink_rejected(self):
        target = self.workspace / STRATEGY
        copy_path = self.root / 'strategy_fg.c'
        target.rename(copy_path)
        target.symlink_to(copy_path)
        with self.assertRaisesRegex(ValueError, 'Escaping path|Symlink path'):
            apply(self.workspace, self.route)


class FrozenInputs(unittest.TestCase):
    def test_final_inputs(self):
        contract, *_ = check(REPO)
        self.assertEqual(len(contract['validation_only_modules']), 47)
        self.assertEqual(contract['runtime_candidate_module_names'], [])


if __name__ == '__main__':
    unittest.main()
