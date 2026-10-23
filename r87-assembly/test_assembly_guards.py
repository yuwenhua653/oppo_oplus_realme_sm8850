#!/usr/bin/env python3
"""Meaningful pre-image gates against the actual healthy R84 loader and CI identity."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
spec = importlib.util.spec_from_file_location('r87_local_assembler', HERE / 'assemble.py')
assembly = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assembly)


class LoaderHandover(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p = subprocess.run(['debugfs', '-R', 'cat /r32/load-modules.sh', str(assembly.BASE / 'vendor_dlkm.img')],
                           capture_output=True, check=True)
        cls.original = p.stdout
        assert assembly.pin(cls.original)['sha256'] == '38cd89544c160f428475608185d963987b20e81858e39ef905f603b4ba692d64'

    def test_actual_owner_switch_preserves_both_surrounding_sections(self):
        result, old, new = assembly.loader_overlay(self.original)
        index = self.original.index(old)
        self.assertEqual(result[:index], self.original[:index])
        self.assertEqual(result[index + len(new):], self.original[index + len(old):])
        self.assertEqual(result.count(b'/vendor_dlkm/r32/r87-mca-start'), 1)
        self.assertNotIn(b'/vendor_dlkm/r32/r70-gauge-load', result)
        self.assertNotIn(b'/vendor_dlkm/r32/r75-mca-start', result)
        self.assertIn(b'normal_requested=249', result)
        self.assertIn(b'r55_late_dsp_start()', result)
        self.assertLess(result.index(b'/vendor_dlkm/r32/r87-mca-start'), result.index(b'setprop vendor.all.modules.ready 1'))

    def test_an_extra_old_owner_invocation_outside_the_switch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Old owners'):
            assembly.loader_overlay(self.original + b'\n/vendor_dlkm/r32/r70-gauge-load\n')

    def test_unknown_owner_blocks_are_rejected(self):
        changed = self.original.replace(b'    # R70: independent readonly telemetry attempt.', b'    # Unknown owner initialization.')
        with self.assertRaisesRegex(ValueError, 'Exact R84'):
            assembly.loader_overlay(changed)


class NoPrematureImage(unittest.TestCase):
    def invoke(self, size=83886080):
        output = HERE / 'must-not-exist-before-new-R87-proof'
        self.assertFalse(output.exists())
        command = [sys.executable, '-B', str(HERE / 'assemble.py'), '--ci', str(WORK / 'r86-success/r86-validation-only'),
                   '--ci-head', assembly.PARENT_R86, '--ci-run', '39726426245', '--abi', str(HERE / 'not-yet-R87-ABI.json'),
                   '--native-contract', str(HERE / 'not-yet-R87-module-set.json'),
                   '--native-review', str(HERE / 'not-yet-R87-native-review.json'),
                   '--native-helper', str(HERE / 'not-yet-R87-helper'), '--build-id', 'R87-MCA-HANDOVER-20261023-01',
                   '--vendor-payload-bytes', str(size), '--out', str(output), '--check-inputs']
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(output.exists())
        return result.stderr

    def test_real_R86_inputs_are_not_an_R87_candidate(self):
        self.assertIn('Actual new R87 commit required', self.invoke())

    def test_unreviewed_RAM_growth_is_rejected_before_output(self):
        self.assertIn('Only explicit 80MiB', self.invoke(92274688))

    def test_recorded_actual_growth_kept_every_reachable_old_inode(self):
        proof = json.loads((HERE / 'PAYLOAD-GROWTH-REVIEW.json').read_text())
        self.assertEqual(proof['status'], 'PASS_EXPLICIT_72_TO_80_MIB_PAYLOAD_GROWTH_ONLY')
        self.assertEqual(proof['source_bytes'], 75497472)
        self.assertEqual(proof['target_bytes'], 83886080)
        self.assertEqual(proof['reserved_internal_inode_changes'], [7])
        self.assertTrue(proof['all_existing_reachable_inode_content_records_identical'])
        self.assertTrue(proof['all_existing_reachable_xattrs_identical'])
        self.assertTrue(proof['double_growth_byte_identical'])
        self.assertEqual(proof['reachable_records'], 278)


if __name__ == '__main__':
    unittest.main()
