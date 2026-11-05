"""Exercise workspace relocation using real temporary Git repositories."""
import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('workspace_layout', HERE / 'workspace_layout.py')
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)


def snapshot(root):
    result = {}
    if not root.exists():
        return result
    for path in root.rglob('*'):
        relative = str(path.relative_to(root))
        if path.is_symlink():
            result[relative] = ('link', os.readlink(path))
        elif path.is_file():
            result[relative] = ('file', path.read_bytes(), path.stat().st_ino)
    return result


class WorkspaceLayoutTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='myron-layout-test-')
        self.addCleanup(self.tmp.cleanup)
        self.rom = Path(self.tmp.name) / 'evo'
        self.entry = self.rom / 'kernel/xiaomi/myron-build'
        self.entry.mkdir(parents=True)
        self.new = self.rom / 'kernel/xiaomi/myron'
        self.old = self.rom / 'out-myron-r123-source/target/product/myron/obj/MYRON_KERNEL/workspace'
        self.lock = {'profile': 'myron-r123-device-validated-dt-source', 'projects': []}
        self.write_lock()
        self.validations = []

    def git(self, root, *args):
        return subprocess.check_output(['git', '-C', str(root), *args], text=True,
                                       stderr=subprocess.DEVNULL).strip()

    def write_lock(self):
        raw = (json.dumps(self.lock, sort_keys=True) + '\n').encode()
        (self.entry / 'sources.lock.json').write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def prepared(self, root):
        source = root / 'common'
        source.mkdir(parents=True)
        self.git(source, 'init', '--quiet')
        self.git(source, 'config', 'user.name', 'Workspace Test')
        self.git(source, 'config', 'user.email', 'workspace-test@example.invalid')
        self.git(source, 'remote', 'add', 'origin', 'https://example.invalid/kernel.git')
        (source / 'Makefile').write_text('VERSION = 6\nPATCHLEVEL = 12\n')
        self.git(source, 'add', 'Makefile')
        self.git(source, 'commit', '--quiet', '-m', 'Fixture source')
        head = self.git(source, 'rev-parse', 'HEAD')
        self.lock['projects'] = [{'path': 'common', 'commit': head,
                                  'url': 'https://example.invalid/kernel.git'}]
        digest = self.write_lock()
        (root / layout.STATE_FILE).write_text(json.dumps(
            {'lock_sha256': digest, 'profile': self.lock['profile']}) + '\n')
        for rel, data in [('out/bazel-integration/cache.bin', b'cache\0unchanged'),
                          ('integration-artifacts/full/objects/Image', b'compiled kernel\0'),
                          ('integration-reports/build-status.json', b'{"success":true}\n')]:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (root / 'bazel-out').symlink_to(root / 'out/bazel-integration')
        return head

    def validate(self, root):
        self.validations.append(root)
        for row in self.lock['projects']:
            project = root / row['path']
            if self.git(project, 'rev-parse', 'HEAD') != row['commit']:
                raise ValueError('Source revision differs')
            if self.git(project, 'status', '--porcelain', '--untracked-files=normal'):
                raise ValueError('Uncommitted source changes')

    def ensure(self, apply=False, **kwargs):
        return layout.ensure_workspace(self.new, self.old, self.entry, apply=apply,
                                       validate_sources=self.validate, **kwargs)

    def test_fresh_dry_run_and_marker_only_repeat(self):
        before = snapshot(self.rom)
        result = self.ensure()
        self.assertEqual(result['action'], 'fresh')
        self.assertFalse(result['prepared'])
        self.assertEqual(snapshot(self.rom), before)
        self.ensure(apply=True)
        self.assertTrue((self.new / '.find-ignore').is_file())
        self.assertFalse(self.old.exists())
        after = snapshot(self.rom)
        self.assertFalse(self.ensure(apply=True)['changed'])
        self.assertEqual(snapshot(self.rom), after)

    def test_move_preserves_git_cache_artifacts_and_old_absolute_alias(self):
        head = self.prepared(self.old)
        original = snapshot(self.old)
        before = snapshot(self.rom)
        planned = self.ensure()
        self.assertEqual(planned['action'], 'migrate')
        self.assertTrue(planned['prepared'])
        self.assertEqual(snapshot(self.rom), before)
        result = self.ensure(apply=True)
        self.assertTrue(result['changed'])
        self.assertTrue(self.old.is_symlink())
        self.assertFalse(self.new.is_symlink())
        self.assertEqual(os.readlink(self.old), os.path.relpath(self.new, self.old.parent))
        self.assertEqual(self.git(self.new / 'common', 'rev-parse', 'HEAD'), head)
        after = snapshot(self.new)
        after.pop('.find-ignore')
        self.assertEqual(after, original)
        self.assertEqual((self.new / 'bazel-out/cache.bin').read_bytes(), b'cache\0unchanged')
        stable = snapshot(self.rom)
        repeated = self.ensure(apply=True)
        self.assertEqual(repeated['action'], 'existing')
        self.assertFalse(repeated['changed'])
        self.assertEqual(snapshot(self.rom), stable)

    def test_existing_prepared_target_gets_marker_and_reuses_other_out(self):
        self.prepared(self.new)
        before = snapshot(self.new)
        result = self.ensure(apply=True)
        self.assertEqual(result['action'], 'existing')
        self.assertTrue(self.old.is_symlink())
        after = snapshot(self.new)
        after.pop('.find-ignore')
        self.assertEqual(after, before)

    def test_missing_legacy_alias_is_repaired_without_replacing_empty_directory(self):
        self.prepared(self.old)
        self.ensure(apply=True)
        self.old.unlink()
        original = snapshot(self.new)
        self.assertTrue(self.ensure()['changed'])
        self.assertFalse(self.old.exists())
        self.ensure(apply=True)
        self.assertTrue(self.old.is_symlink())
        self.assertEqual((self.new / 'bazel-out/cache.bin').read_bytes(), b'cache\0unchanged')
        self.assertEqual(snapshot(self.new), original)
        self.old.unlink()
        self.old.mkdir()
        self.ensure(apply=True)
        self.assertTrue(self.old.is_dir())
        self.assertFalse(self.old.is_symlink())
        self.assertEqual(snapshot(self.new), original)

    def test_dirty_source_and_wrong_lock_stop_before_changes(self):
        self.prepared(self.old)
        (self.old / 'common/Makefile').write_text('Uncommitted local source\n')
        before = snapshot(self.rom)
        with self.assertRaisesRegex(ValueError, 'Uncommitted source'):
            self.ensure(apply=True)
        self.assertEqual(snapshot(self.rom), before)
        self.git(self.old / 'common', 'checkout', '--', 'Makefile')
        (self.old / layout.STATE_FILE).write_text('{"lock_sha256":"wrong","profile":"wrong"}')
        before = snapshot(self.rom)
        with self.assertRaisesRegex(ValueError, 'different source lock'):
            self.ensure(apply=True)
        self.assertEqual(snapshot(self.rom), before)

    def test_two_populated_roots_are_rejected(self):
        self.prepared(self.old)
        self.new.mkdir(parents=True)
        (self.new / 'unknown.txt').write_text('Keep this unrelated data')
        before = snapshot(self.rom)
        with self.assertRaisesRegex(ValueError, 'Both new and legacy'):
            self.ensure(apply=True)
        self.assertEqual(snapshot(self.rom), before)

    def test_redirected_roots_and_wrong_legacy_alias_are_rejected(self):
        self.prepared(self.old)
        self.new.symlink_to(self.old, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Redirected workspace'):
            self.ensure(apply=True)
        self.new.unlink()
        alternate = self.old.with_name('alternate')
        self.old.rename(alternate)
        self.old.symlink_to(alternate, target_is_directory=True)
        before = snapshot(self.rom)
        with self.assertRaisesRegex(ValueError, 'Unexpected legacy'):
            self.ensure(apply=True)
        self.assertEqual(snapshot(self.rom), before)

    def test_nested_destination_is_rejected(self):
        self.prepared(self.old)
        with self.assertRaisesRegex(ValueError, 'non-nested'):
            layout.ensure_workspace(self.old / 'child', self.old, self.entry,
                                    apply=True, validate_sources=self.validate)

    def test_alias_failure_rolls_back_entire_move_and_target_marker(self):
        self.prepared(self.old)
        self.new.mkdir(parents=True)
        (self.new / '.find-ignore').write_text('Existing exclusion\n')
        (self.new / '.find-ignore').chmod(0o640)
        before_old = snapshot(self.old)
        before_new = (self.new / '.find-ignore').read_bytes()
        with patch.object(Path, 'symlink_to', side_effect=OSError('Injected alias failure')):
            with self.assertRaisesRegex(OSError, 'Injected alias failure'):
                self.ensure(apply=True)
        self.assertFalse(self.old.is_symlink())
        self.assertEqual(snapshot(self.old), before_old)
        self.assertEqual((self.new / '.find-ignore').read_bytes(), before_new)
        self.assertEqual((self.new / '.find-ignore').stat().st_mode & 0o777, 0o640)

    def test_cross_device_rename_error_does_not_copy_or_lose_original(self):
        self.prepared(self.old)
        before = snapshot(self.old)
        with patch.object(Path, 'rename', side_effect=OSError(errno.EXDEV, 'Cross-device link')):
            with self.assertRaises(OSError) as caught:
                self.ensure(apply=True)
        self.assertEqual(caught.exception.errno, errno.EXDEV)
        self.assertEqual(snapshot(self.old), before)
        self.assertFalse(self.new.exists())

    def incomplete(self, root):
        self.prepared(root)
        self.lock['projects'].append({'path': 'vendor/qcom/audio', 'commit': 'a' * 40,
                                      'url': 'https://example.invalid/audio.git'})
        digest = self.write_lock()
        (root / layout.STATE_FILE).write_text(json.dumps(
            {'lock_sha256': digest, 'profile': self.lock['profile']}) + '\n')

    def test_interrupted_new_prepare_can_resume_without_writes_in_dry_run(self):
        self.incomplete(self.new)
        before = snapshot(self.rom)
        with self.assertRaisesRegex(ValueError, 'not a self-contained'):
            self.ensure()
        planned = self.ensure(allow_incomplete=True)
        self.assertEqual(planned['action'], 'existing')
        self.assertFalse(planned['prepared'])
        self.assertEqual(snapshot(self.rom), before)
        self.assertEqual(self.validations, [])
        self.ensure(apply=True, allow_incomplete=True)
        self.assertTrue((self.new / '.find-ignore').is_file())

    def test_partial_legacy_is_never_migrated(self):
        self.incomplete(self.old)
        before = snapshot(self.rom)
        with self.assertRaisesRegex(ValueError, 'not a self-contained'):
            self.ensure(apply=True, allow_incomplete=True)
        self.assertEqual(snapshot(self.rom), before)

    def test_dirty_or_changed_origin_partial_sources_are_rejected(self):
        self.incomplete(self.new)
        (self.new / 'common/Makefile').write_text('Uncommitted repair\n')
        before = snapshot(self.rom)
        with self.assertRaisesRegex(ValueError, 'Uncommitted source'):
            self.ensure(apply=True, allow_incomplete=True)
        self.assertEqual(snapshot(self.rom), before)
        self.git(self.new / 'common', 'checkout', '--', 'Makefile')
        self.git(self.new / 'common', 'remote', 'set-url', 'origin', 'https://example.invalid/other.git')
        before = snapshot(self.rom)
        with self.assertRaisesRegex(ValueError, 'origin differs'):
            self.ensure(apply=True, allow_incomplete=True)
        self.assertEqual(snapshot(self.rom), before)

    def test_unowned_partial_entries_or_populated_nonrepo_are_rejected(self):
        self.incomplete(self.new)
        unknown = self.new / 'unowned.txt'
        unknown.write_text('Keep this data\n')
        before = snapshot(self.rom)
        with self.assertRaisesRegex(ValueError, 'Unowned entries'):
            self.ensure(apply=True, allow_incomplete=True)
        self.assertEqual(snapshot(self.rom), before)
        unknown.unlink()
        nonrepo = self.new / 'vendor/qcom/audio'
        nonrepo.mkdir(parents=True)
        (nonrepo / 'audio.c').write_text('Keep this local source\n')
        before = snapshot(self.rom)
        with self.assertRaisesRegex(ValueError, 'not a self-contained'):
            self.ensure(apply=True, allow_incomplete=True)
        self.assertEqual(snapshot(self.rom), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
