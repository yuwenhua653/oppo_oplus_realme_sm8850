#!/usr/bin/env python3
"""Meaningful pre-image gates against the actual healthy R84 loader and CI identity."""
import argparse
import shutil
import tempfile
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
spec = importlib.util.spec_from_file_location('r88_local_assembler', HERE / 'assemble.py')
assembly = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assembly)


BASELINE = PID1 = None


class LoaderHandover(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p = subprocess.run(['debugfs', '-R', 'cat /r32/load-modules.sh', str(BASELINE / 'vendor_dlkm.img')],
                           capture_output=True, check=True)
        cls.original = p.stdout
        assert assembly.pin(cls.original)['sha256'] == '38cd89544c160f428475608185d963987b20e81858e39ef905f603b4ba692d64'

    def test_actual_owner_switch_preserves_both_surrounding_sections(self):
        result, old, new = assembly.loader_overlay(self.original)
        index = self.original.index(old)
        self.assertEqual(result[:index], self.original[:index])
        self.assertEqual(result[index + len(new):], self.original[index + len(old):])
        self.assertEqual(result.count(b'/vendor_dlkm/r32/r88-mca-start'), 1)
        self.assertNotIn(b'/vendor_dlkm/r32/r70-gauge-load', result)
        self.assertNotIn(b'/vendor_dlkm/r32/r75-mca-start', result)
        self.assertIn(b'normal_requested=249', result)
        self.assertIn(b'r55_late_dsp_start()', result)
        self.assertLess(result.index(b'/vendor_dlkm/r32/r88-mca-start'), result.index(b'setprop vendor.all.modules.ready 1'))

    def test_an_extra_old_owner_invocation_outside_the_switch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Old owners'):
            assembly.loader_overlay(self.original + b'\n/vendor_dlkm/r32/r70-gauge-load\n')

    def test_unknown_owner_blocks_are_rejected(self):
        changed = self.original.replace(b'    # R70: independent readonly telemetry attempt.', b'    # Unknown owner initialization.')
        with self.assertRaisesRegex(ValueError, 'Exact R84'):
            assembly.loader_overlay(changed)


class Pid1SourceIdentity(unittest.TestCase):
    def test_exact_reproduced_R84_sources_are_accepted(self):
        assembly.verify_pid1_sources(PID1)

    def test_changed_PID1_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            clone = Path(temp) / 'pid1'
            shutil.copytree(PID1, clone)
            with (clone / 'r36_init.c').open('ab') as stream:
                stream.write(b'\n/* foreign source */\n')
            with self.assertRaisesRegex(ValueError, 'Exact healthy R84 PID1 source required'):
                assembly.verify_pid1_sources(clone)

    def test_added_PID1_include_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            clone = Path(temp) / 'pid1'
            shutil.copytree(PID1, clone)
            (clone / 'foreign.h').write_text('/* unexpected header */\n')
            with self.assertRaisesRegex(ValueError, 'source inventory'):
                assembly.verify_pid1_sources(clone)


class NoPrematureImage(unittest.TestCase):
    def invoke(self, size=83886080):
        output = HERE / 'must-not-exist-before-new-R88-proof'
        self.assertFalse(output.exists())
        command = [sys.executable, '-B', str(HERE / 'assemble.py'), '--ci', str(WORK / 'r87-success/r87-validation-only'),
                   '--ci-head', assembly.OLD_R87_CI, '--ci-run', '39873532978', '--abi', str(HERE / 'not-yet-R88-ABI.json'),
                   '--native-contract', str(HERE / 'not-yet-R88-module-set.json'),
                   '--native-review', str(HERE / 'not-yet-R88-native-review.json'),
                   '--native-helper', str(HERE / 'not-yet-R88-helper'), '--build-id', 'R88-MCA-HANDOVER-20261023-01',
                   '--vendor-payload-bytes', str(size), '--out', str(output), '--check-inputs']
        for name in ('baseline-dir', 'retained-vendor-boot', 'runtime-contract', 'foundation',
                     'pid1-source', 'toolchain', 'reproduction', 'elf-parser'):
            command += ['--' + name, str(HERE / 'missing-reviewed-input')]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(output.exists())
        return result.stderr

    def test_real_R87_inputs_are_not_an_R88_candidate(self):
        self.assertIn('Actual new R88 commit required', self.invoke())

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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-dir', required=True, type=Path)
    parser.add_argument('--pid1-source', required=True, type=Path)
    args, rest = parser.parse_known_args()
    BASELINE = args.baseline_dir.resolve()
    PID1 = args.pid1_source.resolve()
    unittest.main(argv=[sys.argv[0]] + rest)
