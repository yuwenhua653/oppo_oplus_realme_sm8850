#!/usr/bin/env python3
"""Regression tests for the R115 November 1 date-format validation failure."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import build

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


if __name__ == '__main__':
    unittest.main()
