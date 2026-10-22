#!/usr/bin/env python3
"""Exercise R86 exact source overlays and actual-header action provenance."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from apply_control import FULL_BQ, HEADER, PREFIX, QUICKCHG, apply, safe
from build_control import check
from test_source import reconstruct_inputs

REPO = Path(__file__).resolve().parent.parent
ROUTE = REPO / 'r86-build-route'
sys.path.insert(0, str(REPO / 'r61-build-route'))
from action_chain import action_chain


class HeaderActionGuards(unittest.TestCase):
    def setUp(self):
        self.output = 'bazel-out/reviewed/bq27z561.ko'
        self.graph = {'artifacts': [{'id': 1, 'execPath': FULL_BQ}, {'id': 2, 'execPath': HEADER},
                                    {'id': 3, 'execPath': 'bazel-out/reviewed/staging'},
                                    {'id': 4, 'execPath': self.output}],
                      'depSetOfFiles': [{'id': 10, 'directArtifactIds': [1, 2]},
                                       {'id': 11, 'directArtifactIds': [3]}],
                      'actions': [{'mnemonic': 'KernelModule', 'inputDepSetIds': [10], 'outputIds': [3]},
                                  {'mnemonic': 'KernelModuleCpOutputs', 'inputDepSetIds': [11], 'outputIds': [4]}]}

    def test_header_and_c_must_feed_the_same_bq_action(self):
        self.assertEqual(action_chain(self.graph, [FULL_BQ, HEADER], self.output)['kind'], 'staging-copy')

    def test_missing_header_rejected(self):
        self.graph['depSetOfFiles'][0]['directArtifactIds'] = [1]
        with self.assertRaisesRegex(ValueError, 'source-bound'):
            action_chain(self.graph, [FULL_BQ, HEADER], self.output)


class ExactOverlayGuards(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='r86-guards-')
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
        self.assertEqual(apply(self.workspace, self.route, verify=True)['status'], 'PASS_R86_EXACT_POSTIMAGES')

    def test_patch_tamper_rejected(self):
        path = self.route / 'patches/fastcharge-state.patch'
        path.write_bytes(path.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'Patch bytes changed'):
            apply(self.workspace, self.route)

    def test_each_preimage_is_required(self):
        for path in (FULL_BQ, HEADER, QUICKCHG):
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
        with self.assertRaisesRegex(ValueError, 'Only the frozen'):
            apply(self.workspace, self.route)

    def test_source_config_tamper_rejected(self):
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
        target = self.workspace / HEADER
        copy_path = self.root / 'header.h'
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
