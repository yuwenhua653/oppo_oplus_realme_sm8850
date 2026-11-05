"""Exercise adapter upgrades without modifying an actual ROM checkout."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


HERE = Path(__file__).resolve().parent
PREVIOUS = os.environ.get('MYRON_TEST_PREVIOUS_ADAPTER')
ENTRY_PATH = 'kernel/xiaomi/myron-build'


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes()
            for p in root.rglob('*') if p.is_file()}


class AdapterUpgradeTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='myron-adapter-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'adapter'
        shutil.copytree(HERE.parent, self.source,
                        ignore=shutil.ignore_patterns('.git', '__pycache__'))
        self.rom = self.root / 'rom'
        self.target = self.rom / 'device/xiaomi/myron'
        self.target.mkdir(parents=True)
        self.policy = self.target / 'sepolicy/private/local.te'
        self.policy.parent.mkdir(parents=True)
        self.policy.write_bytes(b'# Keep my existing policy.\n')

    def run_adapter(self, apply=False):
        args = [sys.executable, '-B', str(self.source / 'kernel/apply_source_build.py'),
                str(self.rom)]
        if apply:
            args.append('--apply')
        return subprocess.run(args, text=True, capture_output=True)

    def fresh_target(self):
        original = (self.source / 'kernel/upstream-kernel-block.txt').read_text()
        (self.target / 'BoardConfig.mk').write_text(
            '# Existing device configuration\n' + original +
            '# Local recovery setting\nBOARD_LOCAL_SETTING := keep\n')
        dependencies = json.loads((self.source / 'evolution.dependencies').read_text())
        dependencies = [d for d in dependencies if d['target_path'] != ENTRY_PATH]
        (self.target / 'evolution.dependencies').write_text(json.dumps(dependencies))
        (self.target / 'Android.mk').write_text('# Existing Android rules\n')

    def installed_target(self, adapter=None):
        shutil.copytree(adapter or self.source, self.target, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('.git', '__pycache__'))

    def assert_current_kernel(self):
        for path in (self.source / 'kernel').iterdir():
            if path.is_file():
                self.assertEqual((self.target / 'kernel' / path.name).read_bytes(),
                                 path.read_bytes(), path.name)

    def test_fresh_merge_dry_run_then_apply_preserves_local_policy(self):
        self.fresh_target()
        before = snapshot(self.target)
        result = self.run_adapter()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(snapshot(self.target), before)
        result = self.run_adapter(apply=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_current_kernel()
        board = (self.target / 'BoardConfig.mk').read_text()
        self.assertIn('include $(DEVICE_PATH)/kernel/BoardConfigKernel.mk', board)
        self.assertIn('BOARD_LOCAL_SETTING := keep', board)
        self.assertEqual(self.policy.read_bytes(), before['sepolicy/private/local.te'])
        self.assertTrue((self.target / 'Android.mk').read_text().startswith(
            '# Existing Android rules\n'))
        dependencies = json.loads((self.target / 'evolution.dependencies').read_text())
        self.assertEqual(sum(d['target_path'] == ENTRY_PATH for d in dependencies), 1)

    def test_reapplying_current_adapter_is_idempotent(self):
        self.fresh_target()
        self.assertEqual(self.run_adapter(apply=True).returncode, 0)
        before = snapshot(self.target)
        result = self.run_adapter(apply=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith('0 files;'), result.stdout)
        self.assertEqual(snapshot(self.target), before)

    def test_header_repair_survives_adapter_upgrade(self):
        self.installed_target()
        import importlib.util
        spec = importlib.util.spec_from_file_location('merge_headers', HERE / 'apply_source_build.py')
        merger = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(merger)
        board = self.target / 'kernel/BoardConfigKernel.mk'
        repaired = board.read_bytes().replace(merger.HEADER_ANCHOR,
                                              merger.HEADER_ANCHOR + merger.HEADER_CONFIG)
        board.write_bytes(repaired)
        result = self.run_adapter(apply=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(board.read_bytes(), repaired)
        before = snapshot(self.target)
        self.assertEqual(self.run_adapter(apply=True).returncode, 0)
        self.assertEqual(snapshot(self.target), before)
        board.write_bytes(repaired + b'\n# Unknown local kernel edit\n')
        before = snapshot(self.target)
        result = self.run_adapter(apply=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Existing adapter differs:', result.stderr)
        self.assertEqual(snapshot(self.target), before)

    def test_unknown_adapter_change_rejects_before_any_write(self):
        self.installed_target()
        path = self.target / 'kernel/source_dt.py'
        path.write_bytes(path.read_bytes() + b'\n# Unreviewed local customization\n')
        # A different earlier file would otherwise be eligible for replacement.
        old = self.target / 'kernel/BoardConfigKernel.mk'
        old.write_bytes(b'# Reviewed old fixture\n')
        previous = self.source / 'kernel/previous-adapter.json'
        manifest = json.loads(previous.read_text())
        manifest['files'].setdefault(old.name, []).append(
            hashlib.sha256(old.read_bytes()).hexdigest())
        previous.write_text(json.dumps(manifest))
        # Keep the target manifest identical so the actual conflict is source_dt.py.
        (self.target / 'kernel/previous-adapter.json').write_bytes(previous.read_bytes())
        before = snapshot(self.target)
        result = self.run_adapter(apply=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Existing adapter differs:', result.stderr)
        self.assertIn('source_dt.py', result.stderr)
        self.assertEqual(snapshot(self.target), before)

    def test_reviewed_previous_hash_upgrades_without_relaxing_policy(self):
        self.installed_target()
        old = self.target / 'kernel/BoardConfigKernel.mk'
        old.write_bytes(b'# Reviewed old fixture\n')
        previous = self.source / 'kernel/previous-adapter.json'
        manifest = json.loads(previous.read_text())
        manifest['files'].setdefault(old.name, []).append(
            hashlib.sha256(old.read_bytes()).hexdigest())
        previous.write_text(json.dumps(manifest))
        (self.target / 'kernel/previous-adapter.json').write_bytes(previous.read_bytes())
        result = self.run_adapter(apply=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_current_kernel()
        self.assertEqual(self.policy.read_bytes(), b'# Keep my existing policy.\n')

    @unittest.skipUnless(PREVIOUS, 'Set MYRON_TEST_PREVIOUS_ADAPTER to a verified prior checkout')
    def test_published_previous_checkout_upgrade(self):
        prior = Path(PREVIOUS)
        known = json.loads((self.source / 'kernel/previous-adapter.json').read_text())['files']['build.mk']
        prior_build = (prior / 'kernel/build.mk').read_bytes()
        self.assertTrue(prior_build == (self.source / 'kernel/build.mk').read_bytes() or
                        hashlib.sha256(prior_build).hexdigest() in known)
        self.installed_target(prior)
        before = snapshot(self.target)
        dry_run = self.run_adapter()
        self.assertEqual(dry_run.returncode, 0, dry_run.stderr)
        self.assertEqual(snapshot(self.target), before)
        applied = self.run_adapter(apply=True)
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assert_current_kernel()
        self.assertIn('MYRON_DT_MODE ?= source',
                      (self.target / 'kernel/BoardConfigKernel.mk').read_text())
        for name, data in before.items():
            if not name.startswith('kernel/') and name not in (
                    'BoardConfig.mk', 'evolution.dependencies', 'Android.mk'):
                self.assertEqual((self.target / name).read_bytes(), data, name)
        current = snapshot(self.target)
        again = self.run_adapter(apply=True)
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertTrue(again.stdout.startswith('0 files;'), again.stdout)
        self.assertEqual(snapshot(self.target), current)


class ManifestPreflightTest(unittest.TestCase):
    def test_verify_checks_manifest_before_source_or_cache_work(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('manifest_adapter', HERE / 'rom_kernel.py')
        adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(adapter)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            entry = root / 'entry'
            entry.mkdir()
            (entry / 'sources.lock.json').write_text('{"profile": "wrong-fixture"}')
            builder = Mock()
            builder.validate_source_lock.side_effect = ValueError('fixture manifest rejected')
            arguments = ['rom_kernel.py', 'verify', '--entry', str(entry),
                         '--workspace', str(root / 'workspace'), '--dist', str(root / 'dist')]
            with patch.object(sys, 'argv', arguments), \
                    patch.object(sys, 'path', list(sys.path)), \
                    patch.object(adapter, 'entry_check'), \
                    patch.object(adapter, 'load', return_value=builder), \
                    patch.object(adapter.subprocess, 'run') as process:
                with self.assertRaisesRegex(ValueError, 'fixture manifest rejected'):
                    adapter.main()
            builder.validate_source_lock.assert_called_once_with({'profile': 'wrong-fixture'})
            builder.check_sources.assert_not_called()
            process.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
