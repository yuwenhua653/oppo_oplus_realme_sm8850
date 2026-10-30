#!/usr/bin/env python3
"""Host regression tests for readiness build/collection, not a Soong build.

The ELF fixtures are synthetic AArch64 headers and use the real readelf tool.
The shell tests stub envsetup/lunch/m; they never claim Android compilation.
"""
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAMES = ('r99_readiness_broker', 'r99_readiness_client')


def elf_fixture(kind='static'):
    """Minimal non-runnable ELF for testing the collector's file contract."""
    data = bytearray(512)
    data[:16] = b'\x7fELF\x02\x01\x01' + bytes(9)
    extra = kind in ('interpreter', 'needed')
    struct.pack_into('<HHIQQQIHHHHHH', data, 16, 2, 183, 1, 0x400100,
                     64, 0, 0, 64, 56, 3 if extra else 2, 0, 0, 0)
    struct.pack_into('<IIQQQQQQ', data, 64, 1, 7 if kind == 'rwx' else 5,
                     0, 0x400000, 0x400000, len(data), len(data), 4096)
    struct.pack_into('<IIQQQQQQ', data, 120, 0x6474e551,
                     7 if kind == 'execstack' else 6, 0, 0, 0, 0, 0, 16)
    if kind == 'interpreter':
        interp = b'/system/bin/linker64\0'
        data[320:320 + len(interp)] = interp
        struct.pack_into('<IIQQQQQQ', data, 176, 3, 4, 320,
                         0x400140, 0x400140, len(interp), len(interp), 1)
    if kind == 'needed':
        # Real readelf sees DT_NEEDED through PT_DYNAMIC without section headers.
        struct.pack_into('<IIQQQQQQ', data, 176, 2, 4, 320,
                         0x400140, 0x400140, 64, 64, 8)
        struct.pack_into('<QQQQQQQQ', data, 320,
                         1, 1, 5, 0x4001a0, 10, 9, 0, 0)
        data[416:425] = b'\0libc.so\0'
    if kind == 'wrongarch':
        struct.pack_into('<H', data, 18, 62)
    if kind == 'truncated':
        return bytes(data[:80])
    if kind == 'badsegment':
        struct.pack_into('<Q', data, 64 + 32, 513)
    if kind == 'nostack':
        struct.pack_into('<I', data, 120, 0)
    return bytes(data)


class ReadinessBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='r99-readiness-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.controls = self.root/'workspace/tools/myron-r99'
        self.controls.mkdir(parents=True)
        for name in ('prepare-readiness.py', 'collect-readiness.py', 'compile-readiness.sh'):
            shutil.copyfile(HERE/name, self.controls/name)
        shutil.copytree(HERE/'readiness', self.controls/'readiness')
        self.runner = self.root/'runner'
        self.source = self.runner/'r97-aosp'
        self.source.mkdir(parents=True)
        (self.runner/'r99-evidence').mkdir()
        self.product = self.source/'out/target/product/sm8850'
        self.env = dict(os.environ, RUNNER_TEMP=str(self.runner),
                        GITHUB_WORKSPACE=str(self.root/'workspace'))

    def run_python(self, name, *args):
        return subprocess.run(['python3', str(self.controls/name), *map(str, args)],
                              env=self.env, text=True, capture_output=True)

    def outputs(self, kind='static', client_location='system/bin'):
        for name, location in ((NAMES[0], 'system/bin'), (NAMES[1], client_location)):
            p = self.product/location/name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(elf_fixture(kind))

    def test_static_core_build_contract(self):
        bp = re.sub(r'//[^\n]*', '', (HERE/'readiness/Android.bp').read_text())
        blocks = re.findall(r'(cc_defaults|cc_binary)\s*\{([^{}]*)\}', bp)
        self.assertEqual(len(blocks), 3)
        defaults = [body for kind, body in blocks if kind == 'cc_defaults']
        self.assertEqual(len(defaults), 1)
        self.assertRegex(defaults[0], r'static_executable\s*:\s*true\s*,')
        self.assertRegex(defaults[0], r'compile_multilib\s*:\s*"64"\s*,')
        self.assertRegex(defaults[0], r'stl\s*:\s*"none"\s*,')
        binaries = [body for kind, body in blocks if kind == 'cc_binary']
        self.assertEqual({re.search(r'name\s*:\s*"([^"]+)"', b)[1]
                          for b in binaries}, set(NAMES))
        for body in binaries:
            self.assertRegex(body, r'defaults\s*:\s*\["r99_readiness_defaults"\]')
        # An image-specific flag reintroduces unavailable vendor libc variants.
        self.assertNotRegex(bp, r'\b(vendor|proprietary|soc_specific|device_specific|'
                            r'product_specific|system_ext_specific|recovery|ramdisk)\s*:')
        self.assertNotRegex(bp, r'\b(init_rc|vintf_fragments|shared_libs)\s*:')

    def test_prepare_exact_inventory_and_no_overwrite(self):
        check = self.run_python('prepare-readiness.py', '--check-only')
        self.assertEqual(check.returncode, 0, check.stderr)
        prepared = self.run_python('prepare-readiness.py', self.source)
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        manifest = json.loads((self.controls/'readiness/SOURCE-FILES.json').read_text())
        target = self.source/'system/r99_readiness'
        self.assertEqual({p.name for p in target.iterdir()}, {r['path'] for r in manifest})
        for row in manifest:
            self.assertEqual((target/row['path']).read_bytes(),
                             (self.controls/'readiness'/row['path']).read_bytes())
        retry = self.run_python('prepare-readiness.py', self.source)
        self.assertNotEqual(retry.returncode, 0)
        self.assertIn('refusing to overwrite', retry.stderr)

    def test_prepare_rejects_source_drift(self):
        source = self.controls/'readiness/client_main.c'
        source.write_bytes(source.read_bytes() + b'\n')
        result = self.run_python('prepare-readiness.py', self.source)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('readiness source drift', result.stderr)
        self.assertFalse((self.source/'system/r99_readiness').exists())

    def test_collects_both_core_outputs_with_real_readelf(self):
        self.outputs()
        result = self.run_python('collect-readiness.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        deliver = self.runner/'r99-readiness-deliver'
        report = json.loads((deliver/'BUILD-RESULT.json').read_text())
        self.assertEqual({r['build_output'] for r in report['outputs']},
                         {'system/bin/'+name for name in NAMES})
        for row in report['outputs']:
            data = (deliver/row['name']).read_bytes()
            self.assertEqual(row['sha256'], hashlib.sha256(data).hexdigest())
            self.assertTrue(all(row['elf'].values()))
        for name in ('image_built', 'service_installed', 'device_tested',
                     'runtime_placement_qualified', 'property_contexts_installed'):
            self.assertIs(report[name], False)
        self.assertEqual((deliver/'SOURCE-FILES.json').read_bytes(),
                         (self.controls/'readiness/SOURCE-FILES.json').read_bytes())

    def test_vendor_only_output_is_not_a_fallback(self):
        self.outputs(client_location='vendor/bin')
        result = self.run_python('collect-readiness.py')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('missing native output r99_readiness_client', result.stderr)
        self.assertFalse((self.runner/'r99-readiness-deliver/BUILD-RESULT.json').exists())

    def test_symlink_output_rejected(self):
        self.outputs()
        p = self.product/'system/bin'/NAMES[1]
        p.unlink()
        p.symlink_to(NAMES[0])
        result = self.run_python('collect-readiness.py')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('missing native output', result.stderr)

    def test_invalid_elf_outputs_rejected(self):
        errors = {'interpreter': 'dynamic interpreter',
                  'needed': 'unexpected dynamic dependency',
                  'rwx': 'unsafe load segment', 'execstack': 'executable stack',
                  'wrongarch': 'not ELF64 AArch64', 'truncated': 'program headers',
                  'badsegment': 'segment geometry', 'nostack': 'GNU stack absent'}
        for kind, error in errors.items():
            with self.subTest(kind=kind):
                shutil.rmtree(self.runner/'r99-readiness-deliver', ignore_errors=True)
                self.outputs(kind)
                result = self.run_python('collect-readiness.py')
                self.assertNotEqual(result.returncode, 0, kind)
                self.assertIn(error, result.stderr)
                self.assertFalse((self.runner/'r99-readiness-deliver/BUILD-RESULT.json').exists())

    def shell_fixture(self, stage='success', code=0, kind='static'):
        build = self.source/'build'
        build.mkdir()
        fixture = self.runner/'fixture.elf'
        fixture.write_bytes(elf_fixture(kind))
        script = '''
lunch() { printf '%s\\n' "$*" > "$RUNNER_TEMP/lunch.args"; return "${TEST_LUNCH_RC:-0}"; }
m() {
    printf '%s\\n' "$*" > "$RUNNER_TEMP/m.args"
    [ -f system/r99_readiness/Android.bp ] || return 95
    [ "${TEST_M_RC:-0}" -eq 0 ] || return "$TEST_M_RC"
    mkdir -p out/target/product/sm8850/system/bin
    cp "$RUNNER_TEMP/fixture.elf" out/target/product/sm8850/system/bin/r99_readiness_broker
    cp "$RUNNER_TEMP/fixture.elf" out/target/product/sm8850/system/bin/r99_readiness_client
}
return "${TEST_ENV_RC:-0}"
'''
        (build/'envsetup.sh').write_text(script)
        self.env['R99_BUILD_JOBS'] = '3'
        if stage != 'success':
            self.env['TEST_'+stage.upper()+'_RC'] = str(code)
        return subprocess.run(['bash', str(self.controls/'compile-readiness.sh')],
                              env=self.env, text=True, capture_output=True)

    def test_shell_success_collects_both_outputs(self):
        result = self.shell_fixture()
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual((self.runner/'lunch.args').read_text(), 'twrp_sm8850\n')
        self.assertEqual((self.runner/'m.args').read_text(),
                         '-j3 r99_readiness_broker r99_readiness_client\n')
        self.assertEqual((self.runner/'r99-evidence/readiness-compiler-exit-code.txt').read_text(), '0\n')
        self.assertTrue((self.runner/'r99-readiness-deliver/BUILD-RESULT.json').is_file())

    def test_shell_compiler_failure_preserves_status_and_stops_collection(self):
        result = self.shell_fixture('m', 63)
        self.assertEqual(result.returncode, 63, result.stderr + result.stdout)
        self.assertEqual((self.runner/'r99-evidence/readiness-compiler-exit-code.txt').read_text(), '63\n')
        self.assertFalse((self.runner/'r99-readiness-deliver').exists())

    def test_shell_envsetup_failure_stops_before_lunch(self):
        result = self.shell_fixture('env', 61)
        self.assertEqual(result.returncode, 61, result.stderr + result.stdout)
        self.assertFalse((self.runner/'lunch.args').exists())
        self.assertFalse((self.runner/'m.args').exists())

    def test_shell_lunch_failure_stops_before_compile(self):
        result = self.shell_fixture('lunch', 62)
        self.assertEqual(result.returncode, 62, result.stderr + result.stdout)
        self.assertFalse((self.runner/'m.args').exists())
        self.assertFalse((self.runner/'r99-readiness-deliver').exists())

    def test_shell_source_drift_stops_before_build(self):
        p = self.controls/'readiness/watchdog.c'
        p.write_bytes(p.read_bytes() + b'\n')
        result = self.shell_fixture()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('readiness source drift', result.stdout)
        self.assertFalse((self.runner/'lunch.args').exists())
        self.assertFalse((self.runner/'m.args').exists())

    def test_shell_collection_failure_is_not_success(self):
        result = self.shell_fixture(kind='interpreter')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('dynamic interpreter', result.stdout)
        self.assertEqual((self.runner/'r99-evidence/readiness-compiler-exit-code.txt').read_text(), '0\n')
        self.assertFalse((self.runner/'r99-readiness-deliver/BUILD-RESULT.json').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
