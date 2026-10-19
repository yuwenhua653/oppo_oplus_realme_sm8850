#!/usr/bin/env python3
"""Reproduce R78's execroot path failure with the pinned upstream flattener."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PREFIX = 'vendor/qcom/sm8850/'
DRIVER = 'drivers/xiaomi/myron_tfa98xx/Kconfig'
FRAGMENT = ROOT / 'audio/fragments/Kconfig'
PAYLOAD = ROOT / ('audio/payload/' + DRIVER)
FIXTURE = HERE / 'fixtures/flatten_kconfig.sh'
CORRECT_SOURCE = 'source "$(KCONFIG_EXT_PREFIX)' + DRIVER + '"'
OLD_SOURCE = 'source "' + DRIVER + '"'


class KconfigFlatten(unittest.TestCase):
    def flatten(self, fragment):
        with tempfile.TemporaryDirectory(prefix='r78-kconfig-execroot-') as temporary:
            execroot = Path(temporary)
            package = execroot / PREFIX
            driver = package / DRIVER
            driver.parent.mkdir(parents=True)
            shutil.copyfile(PAYLOAD, driver)
            entry = package / 'drivers/xiaomi/myron/Kconfig'
            entry.parent.mkdir(parents=True)
            entry.write_text(fragment)
            (package / 'Kconfig.msm').write_text(
                'source "$(KCONFIG_EXT_PREFIX)drivers/xiaomi/myron/Kconfig"\n')
            script = package / 'flatten_kconfig.sh'
            shutil.copyfile(FIXTURE, script)
            script.chmod(0o755)
            # The real Bazel action runs from execroot and exports this prefix.
            # In both cases the payload already exists at its declared input path.
            self.assertTrue(driver.is_file())
            self.assertFalse((execroot / DRIVER).exists())
            return subprocess.run(
                ['bash', PREFIX + 'flatten_kconfig.sh', PREFIX + 'Kconfig.msm'],
                cwd=execroot,
                env={**os.environ, 'KCONFIG_EXT_PREFIX': PREFIX},
                capture_output=True,
                text=True,
                timeout=10,
                check=False)

    def test_fixture_is_the_pinned_upstream_file(self):
        provenance = json.loads((HERE / 'fixtures/PROVENANCE.json').read_text())
        data = FIXTURE.read_bytes()
        self.assertEqual(provenance['repository'], 'LineageOS/android_kernel_qcom_sm8850')
        self.assertEqual(provenance['commit'], '557159b6a0d06f1c6f07ec4c1f22bc9309a113e4')
        self.assertEqual(provenance['path'], 'flatten_kconfig.sh')
        self.assertEqual(provenance['bytes'], len(data))
        self.assertEqual(provenance['sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(provenance['git_blob_sha1'],
                         hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest())

    def test_old_bare_source_fails_despite_payload_present(self):
        fragment = FRAGMENT.read_text()
        self.assertEqual(fragment.count(CORRECT_SOURCE), 1)
        broken = fragment.replace(CORRECT_SOURCE, OLD_SOURCE)
        result = self.flatten(broken)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(DRIVER, result.stderr)
        self.assertNotIn('config MYRON_TFA98XX', result.stdout)

    def test_production_fragment_resolves_payload_exactly_once(self):
        fragment = FRAGMENT.read_text()
        self.assertEqual(fragment.count(CORRECT_SOURCE), 1)
        result = self.flatten(fragment)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertEqual(len(re.findall(r'^config MYRON_TFA98XX$', result.stdout, re.M)), 1)
        self.assertEqual(result.stdout.count(PAYLOAD.read_text()), 1)
        self.assertNotRegex(result.stdout, r'(?m)^\s*source\s')


if __name__ == '__main__':
    unittest.main(verbosity=2)
