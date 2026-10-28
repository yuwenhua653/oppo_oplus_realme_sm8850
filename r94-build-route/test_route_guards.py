#!/usr/bin/env python3
"""Host guard tests only; do not execute inherited prep, Bazel or phone code."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import build_led as b
import prepare_r92 as prep

ROOT = Path(__file__).resolve().parent
REPO = Path(os.environ.get('R94_TEST_REPO', ROOT.parent))


class Guards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'payload').mkdir()
        (self.root / 'tests').mkdir()
        self.payload = b'/* fixture only; never a kernel patch */\n'
        self.test = b'# fixture only\n'
        (self.root / 'payload/leds-qcom-flash.c').write_bytes(self.payload)
        (self.root / 'tests/source.py').write_bytes(self.test)
        self.contract = {'schema': 1, 'status': 'FROZEN_REVIEWED_SOURCE',
            'compile_only': True, 'flashable': False, 'activation_allowed': False,
            'source': b.SOURCE, 'before': b.BEFORE, 'after': b.pin(self.payload),
            'payload': 'payload/leds-qcom-flash.c',
            'source_tests': [{'file': 'tests/source.py', **b.pin(self.test)}],
            'test_inputs': [{'file': 'tests/source.py', **b.pin(self.test)}]}

    def tearDown(self):
        self.tmp.cleanup()

    def save(self):
        (self.root / 'LED-PATCH.json').write_text(json.dumps(self.contract))

    def check(self):
        self.save()
        return b.check_patch(self.root)

    def test_valid_fixture_contract(self):
        self.assertEqual(self.check(), self.contract)

    def test_pending_draft_fails_before_any_repo_or_workspace_access(self):
        self.contract['status'] = 'PENDING_IMPLEMENTATION'
        self.save()
        result = subprocess.run([sys.executable, '-B', str(ROOT/'build_led.py'),
            '--route', str(self.root),
            '--repo-root', str(self.root/'no-repo'), '--workspace', str(self.root/'never-created'),
            '--check-inputs'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('LED patch is pending', result.stderr)
        self.assertFalse((self.root/'never-created').exists())

    def test_wrong_source_scope(self):
        self.contract['source'] = 'vendor/qcom/sm8850/drivers/power/supply/qti_battery_charger.c'
        with self.assertRaisesRegex(ValueError, 'Only the exact'):
            self.check()

    def test_wrong_preimage(self):
        self.contract['before'] = {'bytes': 1, 'sha256': '0'*64}
        with self.assertRaisesRegex(ValueError, 'Only the exact'):
            self.check()

    def test_unimplemented_payload(self):
        self.contract['after'] = None
        with self.assertRaisesRegex(ValueError, 'Real reviewed'):
            self.check()

    def test_same_payload(self):
        self.contract['after'] = b.BEFORE
        with self.assertRaisesRegex(ValueError, 'Real reviewed'):
            self.check()

    def test_payload_mismatch(self):
        (self.root/'payload/leds-qcom-flash.c').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'payload pin'):
            self.check()

    def test_redirected_payload(self):
        p = self.root/'payload/leds-qcom-flash.c'; p.unlink()
        p.symlink_to(self.root/'tests/source.py')
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            self.check()

    def test_missing_tests(self):
        self.contract['source_tests'] = []
        with self.assertRaisesRegex(ValueError, 'actual-source tests'):
            self.check()

    def test_changed_tests(self):
        (self.root/'tests/source.py').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'test pin'):
            self.check()

    def test_unpinned_test_support_rejected(self):
        (self.root/'tests/host_shim.h').write_text('unreviewed')
        with self.assertRaisesRegex(ValueError, 'test input inventory'):
            self.check()

    def test_changed_test_support_rejected(self):
        self.contract['test_inputs'].append({'file': 'tests/host_shim.h', **b.pin(b'reviewed')})
        (self.root/'tests/host_shim.h').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'support pin'):
            self.check()

    def test_duplicate_tests(self):
        self.contract['source_tests'] *= 2
        with self.assertRaisesRegex(ValueError, 'unique Python'):
            self.check()

    def test_active_policy_forbidden(self):
        for key, value in [('compile_only', False), ('flashable', True), ('activation_allowed', True)]:
            with self.subTest(key=key):
                old = self.contract[key]; self.contract[key] = value
                with self.assertRaisesRegex(ValueError, 'inactive'):
                    self.check()
                self.contract[key] = old

    def test_build_requests_only_led_plus_frozen_core(self):
        x = b.plan(['bazel'], ['--nokeep_going'],
                   ['//common:kernel_aarch64', '//myron_artifact_metadata:kernel_release'])
        self.assertEqual([s for s in x['build'] if s.startswith('//')], [b.MODULE['target'],
            '//common:kernel_aarch64', '//myron_artifact_metadata:kernel_release'])
        self.assertNotIn('mca', ' '.join(x['build']))
        self.assertNotIn('camera', ' '.join(x['build']))
        self.assertEqual(x['analysis'][-1], 'deps(' + b.MODULE['target'] + ')')

    def test_changed_core_targets(self):
        with self.assertRaisesRegex(ValueError, 'core metadata'):
            b.plan([], [], ['//vendor/qcom/sm8850:canoe_perf'])

    def test_filename_and_elf_identity_are_separate(self):
        class Resolver:
            def resolve(_, graph, module):
                self.assertEqual(module['module_name'], 'leds-qcom-flash')
                return dict(module, output='bazel-out/leds-qcom-flash.ko', symvers='bazel-out/a.symvers')
        x = b.resolve_led({}, Resolver())
        self.assertEqual(x['module_name'], 'leds_qcom_flash')
        self.assertEqual(x['output'], 'bazel-out/leds-qcom-flash.ko')

    def test_safe_paths(self):
        for path in ('/etc/passwd', '../escape', ''):
            with self.subTest(path=path), self.assertRaises(ValueError):
                b.safe(self.root, path)

    def test_realistic_bazel_out_symlink_allowed_for_generated_only(self):
        output_tree = self.root/'out/bazel-integration/execroot/__main__/bazel-out'
        output_tree.mkdir(parents=True)
        (self.root/'bazel-out').symlink_to(output_tree, target_is_directory=True)
        relative = 'bazel-out/aarch64-fastbuild/bin/common/kernel_aarch64/kernel_aarch64_dot_config'
        path = self.root/relative; path.parent.mkdir(parents=True); path.write_bytes(b'actual fixture')
        self.assertEqual(b.generated(self.root, relative).read_bytes(), b'actual fixture')
        with self.assertRaisesRegex(ValueError, 'Symlink source'):
            b.safe(self.root, relative)

    def test_bazel_symlink_to_arbitrary_tree_rejected(self):
        other = self.root/'arbitrary'; other.mkdir(); (other/'data').write_bytes(b'bad')
        (self.root/'bazel-out').symlink_to(other, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'pinned output base'):
            b.generated(self.root, 'bazel-out/data')

    def test_generated_nested_escape_rejected(self):
        tree = self.root/'out/bazel-integration/execroot/__main__/bazel-out'; tree.mkdir(parents=True)
        (self.root/'bazel-out').symlink_to(tree, target_is_directory=True)
        other = self.root/'secret'; other.write_bytes(b'bad')
        (tree/'data').symlink_to(other)
        with self.assertRaisesRegex(ValueError, 'artifact escapes'):
            b.generated(self.root, 'bazel-out/data')

    def test_generated_rejects_source_and_traversal(self):
        for path in ('source.c', '/etc/passwd', 'bazel-out/../escape'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                b.generated(self.root, path)

    def test_exact_frozen_preparation_prefix(self):
        data = (REPO/'r88-build-route/build_fg_policy.py').read_bytes()
        nodes = prep.preparation_statements(data)
        source = ast.unparse(ast.Module(body=nodes, type_ignores=[]))
        self.assertIn('r60', source); self.assertIn('r61', source)
        for name in ('apply_thermal', 'apply_multimedia', 'apply_repairs', 'r83', 'r84', 'r85', 'r86', 'r87'):
            self.assertIn(name, source)
        self.assertIn('verify_postimages(root, repo, pc, parent_inputs, r84, route)', source)
        self.assertNotIn('runner.build_targets(', source)
        self.assertNotIn('aquery', source)
        self.assertNotIn('validation_build', source)

    def test_changed_preparation_rejected(self):
        data = (REPO/'r88-build-route/build_fg_policy.py').read_bytes()
        with self.assertRaisesRegex(ValueError, 'engine changed'):
            prep.preparation_statements(data + b'\n')

    def test_missing_config_graph_fails(self):
        with self.assertRaisesRegex(ValueError, 'One shared config'):
            b.verify_config(self.root, {})


if __name__ == '__main__':
    unittest.main(verbosity=2)
