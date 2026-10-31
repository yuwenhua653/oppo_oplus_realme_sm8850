#!/usr/bin/env python3
"""Check metadata using the pinned upstream implementation and real Git repos."""
import ast
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import build_full as b
import dt_sandbox

HERE=Path(__file__).resolve().parent
REFERENCE=HERE/'reference/workspace_status_stamp.py'
assert b.sha(REFERENCE)=='6ec292d3bc656a9403766bbbb367cc5856cbc9c5f495c3b6653e10e7ed301b50'
upstream=b.load('r114_actual_upstream_stamp',REFERENCE)

class Route(unittest.TestCase):
    def test_dt_sandbox_rejects_missing_fingerprint_and_accepts_complete_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            dt=Path(td)
            for name in ('Makefile','qcom/fingerprint/Kbuild','qcom/fingerprint/Makefile',
                         'qcom/fingerprint/canoe-fingerprint.dts','qcom/fingerprint/canoe-fingerprint.dtsi'):
                p=dt/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture')
            expected=dt_sandbox.expected_inputs(dt)
            self.assertEqual(len(expected),5)
            with self.assertRaisesRegex(ValueError,'fingerprint/Kbuild'):
                dt_sandbox.check_inputs(expected,dt_sandbox.DT+'/Makefile\n')
            self.assertTrue(dt_sandbox.check_inputs(expected,'\n'.join(sorted(expected)))['success'])

    def test_real_git_commit_and_dirty_suffix(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ,{'BUILD_NUMBER':''}):
            p=Path(td)
            subprocess.run(['git','init','-q',str(p)],check=True)
            (p/'source.c').write_text('int a;\n')
            subprocess.run(['git','-C',str(p),'add','source.c'],check=True)
            subprocess.run(['git','-C',str(p),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture'],check=True)
            head=b.git(p,'rev-parse','HEAD')
            self.assertEqual(upstream.get_localversion_from_git(p).collect(),'-g'+head[:12])
            (p/'source.c').write_text('int b;\n')
            self.assertEqual(upstream.get_localversion_from_git(p).collect(),'-g'+head[:12]+'-dirty')

    def test_actual_upstream_uses_current_override(self):
        with patch.dict(os.environ,{},clear=True):
            clock=b.start_clock(1793445600)
            instance=object.__new__(upstream.Stamp)
            result=instance.async_get_source_date_epoch(Path('not-a-git-project'))
            self.assertEqual(result.collect(),str(clock['epoch']))
            self.assertIn('2026',clock['kbuild_timestamp'])

    def test_reject_fixed_versions(self):
        for value in ['6.12.81-android16-6-maybe-dirty-4k','6.12.81-android16-6-mybe-4k',
                      '6.12.81-android16-6-g000000000000-4k','6.12.23-android16-6-g'+b.CORE_HEAD[:12]+'-4k']:
            with self.subTest(value=value),self.assertRaises(ValueError):b.validate_release(value,b.CORE_HEAD)

    def test_accept_actual_commit_clean_and_dirty(self):
        for suffix in ['', '-dirty']:
            b.validate_release('6.12.81-android16-6-g'+b.CORE_HEAD[:12]+suffix+'-4k',b.CORE_HEAD)

    def test_reject_time_and_version_hijacks(self):
        for key in ['FAKETIME','FAKESTAT','LD_PRELOAD','LOCALVERSION','BUILD_NUMBER']:
            with self.subTest(key=key),patch.dict(os.environ,{key:'unexpected'},clear=True),self.assertRaises(ValueError):b.start_clock()

    def test_banner_checked_against_real_clock(self):
        release='6.12.81-android16-6-g'+b.CORE_HEAD[:12]+'-4k'
        with tempfile.TemporaryDirectory() as td,patch.dict(os.environ,{},clear=True):
            clock=b.start_clock(1793445600);p=Path(td)/'Image'
            p.write_bytes(('Linux version '+release+' (test) #1 SMP '+clock['kbuild_timestamp']+'\0').encode())
            b.verify_banner(p,release,clock)
            p.write_bytes(('Linux version '+release+' (test) #1 SMP Thu Jan 01 00:00:00 UTC 1970\0').encode())
            with self.assertRaises(ValueError):b.verify_banner(p,release,clock)

    def test_one_stamp_configuration_for_build_and_query(self):
        self.assertEqual(b.stamped_options(['--jobs=2']),['--jobs=2','--config=stamp'])
        for arg in ['--nostamp','--config=stamp','--workspace_status_command=false']:
            with self.assertRaises(ValueError):b.stamped_options([arg])

    def test_full_graph_and_all_existing_repairs_are_requested(self):
        source=(HERE/'build_full.py').read_text();ast.parse(source)
        for value in ["build_targets(root,'full')",'kernel_aarch64_modules','validation_only_modules',
                      'apply_soccp.py','apply_dsp_auto_boot.py','r81-build-route/apply_wifi.py',
                      'r82-build-route/apply_cnss.py','led.patch_source','led.prepare']:
            self.assertIn(value,source)
        self.assertNotIn('r80-build-route/apply_wifi.py',source)

    def test_dt_merge_inputs_reject_conflicts_corruption_and_escape(self):
        with tempfile.TemporaryDirectory() as td:
            output=Path(td)/'output';output.mkdir()
            rows=[]
            for folder in ('one','two'):
                p=output/folder/'test.dtbo';p.parent.mkdir();p.write_bytes(b'same')
                rows.append({'file':str(p.relative_to(output)),'sha256':b.sha(p)})
            manifest=output/'artifact-manifest.json'
            b.write(manifest,{'flashable':False,'files':rows})
            self.assertEqual(len(b.dt_inputs(output,['test.dtbo'])),1)
            p.write_bytes(b'corrupted')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):b.dt_inputs(output,['test.dtbo'])
            rows[-1]['sha256']=b.sha(p)
            b.write(manifest,{'flashable':False,'files':rows})
            with self.assertRaisesRegex(ValueError,'Conflicting'):b.dt_inputs(output,['test.dtbo'])
            rows[-1]['file']='../test.dtbo'
            b.write(manifest,{'flashable':False,'files':rows})
            with self.assertRaisesRegex(ValueError,'Unsafe'):b.dt_inputs(output,['test.dtbo'])

if __name__=='__main__':unittest.main(verbosity=2)
