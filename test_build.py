#!/usr/bin/env python3
"""Regression tests for source-lock admission and kernel build provenance."""
import contextlib
import datetime
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import build
import sync_sources

HERE = Path(__file__).resolve().parent
HEAD = '6af5fb53d676bc20d6eaeabe31c1b7418c38a679'
RELEASE = '6.12.81-android16-6-g' + HEAD[:12] + '-4k'


class BannerTests(unittest.TestCase):
    def image(self, path, stamp):
        path.write_bytes(b'Image\0Linux version ' + RELEASE.encode() +
                         b' (build-user@build-host) (clang) #1 SMP PREEMPT ' + stamp.encode() + b'\0')

    def clock(self, epoch):
        with patch.dict(os.environ, {}, clear=True):
            return build.start_clock(epoch)

    def test_upstream_gnu_date_every_day(self):
        with tempfile.TemporaryDirectory() as t:
            image = Path(t) / 'Image'
            for day in range(1, 32):
                month = 11 if day <= 30 else 10
                epoch = int(datetime.datetime(2026, month, day, 2, 11, 41,
                                              tzinfo=datetime.timezone.utc).timestamp())
                # Same command/environment as pinned Kleaf _setup_env.sh.
                stamp = subprocess.check_output(['date', '-d', '@' + str(epoch)],
                    env={**os.environ, 'TZ': 'UTC', 'LC_ALL': 'C'}, text=True).strip()
                clock = self.clock(epoch)
                self.assertEqual(clock['kbuild_timestamp'], stamp)
                self.image(image, stamp)
                build.verify_banner(image, RELEASE, clock)
                self.image(image, datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc)
                           .strftime('%a %b %d %H:%M:%S UTC %Y'))
                build.verify_banner(image, RELEASE, clock)

    def test_exact_failed_epoch_and_reject_wrong_time(self):
        clock = self.clock(1793499101)
        with tempfile.TemporaryDirectory() as t:
            image = Path(t) / 'Image'
            self.image(image, 'Sun Nov  1 02:11:41 UTC 2026')
            self.assertNotIn('Sun Nov 01 02:11:41 UTC 2026', image.read_text())
            build.verify_banner(image, RELEASE, clock)
            for bad in ['Sun Nov  1 02:11:42 UTC 2026', 'Sat Oct 31 02:11:41 UTC 2026',
                        'Mon Nov  1 02:11:41 UTC 2026', 'Sun Nov  1 10:11:41 CST 2026']:
                self.image(image, bad)
                with self.assertRaises(ValueError):
                    build.verify_banner(image, RELEASE, clock)

    def test_preflight_saves_failed_banner_and_success(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            reports = root / 'reports'
            reports.mkdir()
            (root / 'kernel.release').write_text(RELEASE)
            self.image(root / 'Image', 'Sun Nov  1 02:11:42 UTC 2026')
            clock = self.clock(1793499101)
            with self.assertRaises(ValueError):
                build.check_kernel_before_modules(root, ['Image', 'kernel.release'], HEAD, clock, reports)
            record = json.loads((reports / 'kernel-preflight.json').read_text())
            self.assertFalse(record['verified'])
            self.assertIn('02:11:42', record['linux_banners'][0])
            self.assertTrue((root / 'integration-artifacts/kernel-diagnostic/Image').is_file())
            self.image(root / 'Image', 'Sun Nov  1 02:11:41 UTC 2026')
            self.assertTrue(build.check_kernel_before_modules(root, ['Image', 'kernel.release'],
                                                             HEAD, clock, reports)['verified'])


class SourceManifestTests(unittest.TestCase):
    def test_checked_in_lock_is_accepted_without_changes(self):
        raw = (HERE / 'sources.lock.json').read_bytes()
        lock = json.loads(raw)
        before = json.dumps(lock, sort_keys=True)
        build.validate_source_lock(lock)
        self.assertEqual(json.dumps(lock, sort_keys=True), before)
        self.assertEqual((HERE / 'sources.lock.json').read_bytes(), raw)

    def test_other_profiles_and_missing_profile_are_rejected(self):
        for lock in ({'profile': 'myron-r115-clean-source'},
                     {'profile': 'another-device'}, {}, {'profile': None}):
            with self.subTest(lock=lock):
                with self.assertRaises(ValueError) as caught:
                    build.validate_source_lock(lock)
                self.assertIn('expected profile ' + repr(build.SOURCE_PROFILE), str(caught.exception))
                self.assertIn('got ' + repr(lock.get('profile')), str(caught.exception))

    def test_no_sync_main_reaches_sources_with_checked_in_lock(self):
        # Exercise the real entry path and its real checked-in lock. Stop at
        # the first source operation, before any fetching or compilation.
        boundary = 'test stopped at source linking'
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / 'workspace'
            arguments = ['build.py', '--workspace', str(workspace), '--no-sync',
                         '--jobs', '2', '--ram-mb', '10000']
            with patch('sys.argv', arguments), \
                    patch.object(build, 'git', return_value='0' * 40), \
                    patch.object(build, 'logged') as logged, \
                    patch.object(build, 'check_sources') as check_sources, \
                    patch.object(sync_sources, 'link_sources',
                                 side_effect=RuntimeError(boundary)) as link_sources, \
                    contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                result = build.main()
            self.assertEqual(result, 1)
            link_sources.assert_called_once_with(
                workspace.resolve(), json.loads((HERE / 'sources.lock.json').read_text()))
            logged.assert_not_called()
            check_sources.assert_not_called()
            state = json.loads((workspace / 'integration-reports/build-status.json').read_text())
            self.assertEqual(state['error'], boundary)
            self.assertEqual(state['phase'], 'failed')
            self.assertFalse(state['success'])
            self.assertFalse(state['compiled'])


if __name__ == '__main__':
    unittest.main()
