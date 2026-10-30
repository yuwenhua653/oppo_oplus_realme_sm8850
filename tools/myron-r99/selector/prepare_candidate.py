#!/usr/bin/env python3
"""Pin and test a Recovery-only mode selector; this does not build Android init."""
import difflib
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SELINUX_SHA = 'd1d685a4f4616f4cf5d117bd09f3685a2a4267303431200ed27132718032acbe'
BP_SHA = '2216f167ad714e6dba9e38bc90c1bd51c0b431dc6ff97c79a0d8ebea154e9cfd'
COMMIT = 'b6e6bf192be2c4341d5dac41ccfa634d2d684816'


def digest(b):
    return hashlib.sha256(b).hexdigest()


def pinned(name, sha):
    b = (ROOT / 'baseline' / name).read_bytes()
    assert digest(b) == sha, 'baseline changed: ' + name
    return b.decode()


def brace_block(text, offset):
    start = text.index('{', offset)
    level = 1
    end = start + 1
    while level:
        level += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[offset:end]


def module(bp, name):
    match = re.search(r'(?m)^cc_[a-z_]+\s*\{\s*name:\s*"' + re.escape(name) + '"', bp)
    assert match, 'module absent: ' + name
    return brace_block(bp, match.start())


def main():
    source = pinned('selinux.cpp', SELINUX_SHA)
    bp = pinned('Android.bp', BP_SHA)
    defaults = module(bp, 'libinit_defaults')
    assert 'srcs: init_common_sources + init_device_sources,' in defaults
    assert re.search(r'target:\s*\{\s*recovery:\s*\{\s*cflags:\s*\["-DRECOVERY"\]', defaults)
    assert '"selinux.cpp"' in bp[bp.index('init_device_sources = ['):bp.index(']', bp.index('init_device_sources = ['))]
    assert 'defaults: ["libinit_defaults"]' in module(bp, 'libinit')
    recovery = module(bp, 'init_second_stage.recovery')
    assert 'static_libs: ["libinit"]' in recovery and 'recovery: true' in recovery
    assert 'cflags: ["-DRECOVERY"]' in recovery
    normal = module(bp, 'init_second_stage')
    assert 'static_libs: ["libinit"]' in normal and 'RECOVERY' not in normal
    anchor = '    bool is_enforcing = IsEnforcing();\n'
    assert source.count(anchor) == 1
    added = ('#ifdef RECOVERY\n'
             '    // Android and Recovery share bootconfig on this device. Keep the\n'
             '    // existing Recovery permissive mode independent of the Android selector.\n'
             '    is_enforcing = false;\n'
             '#endif\n')
    candidate = source.replace(anchor, anchor + added, 1)
    (ROOT / 'selinux.cpp').write_text(candidate)
    (ROOT / 'recovery-only-permissive.patch').write_text(''.join(difflib.unified_diff(
        source.splitlines(keepends=True), candidate.splitlines(keepends=True),
        fromfile='a/init/selinux.cpp', tofile='b/init/selinux.cpp')))
    with tempfile.TemporaryDirectory(prefix='patch-check-', dir=ROOT) as check:
        target = Path(check) / 'init/selinux.cpp'
        target.parent.mkdir()
        target.write_text(source)
        patch = str(ROOT / 'recovery-only-permissive.patch')
        subprocess.run(['git', 'apply', '--check', patch], cwd=check, check=True, capture_output=True)
        subprocess.run(['git', 'apply', patch], cwd=check, check=True, capture_output=True)
        assert target.read_text() == candidate, 'patch application differs from candidate'
    function = brace_block(candidate, candidate.index('void SelinuxSetEnforcement()'))
    # Compile the exact production function, replacing only its platform API/log
    # boundaries. The tests neither reimplement nor copy the decision body.
    stub = (ROOT / 'test_harness.cpp.in').read_text()
    assert stub.count('/* PRODUCTION_FUNCTION */') == 1
    generated = stub.replace('/* PRODUCTION_FUNCTION */', function)
    (ROOT / 'test_extracted_function.cpp').write_text(generated)
    results = []
    with tempfile.TemporaryDirectory(prefix='r99-selector-tests-') as test_root:
        for name, define in [('normal', []), ('recovery', ['-DRECOVERY'])]:
            binary = Path(test_root) / ('test_' + name)
            argv = ['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-O1', '-g',
                    '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-no-pie',
                    *define, str(ROOT / 'test_extracted_function.cpp'), '-o', str(binary)]
            subprocess.run(argv, check=True, capture_output=True)
            import os
            env = {**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0:abort_on_error=1', 'UBSAN_OPTIONS': 'halt_on_error=1'}
            run = subprocess.run([str(binary)], check=True, capture_output=True, text=True, env=env)
            results.append({'variant': name, 'cases': 8, 'result': run.stdout.strip()})
    review = {
        'status': 'SOURCE_CANDIDATE_AND_EXTRACTED_FUNCTION_TESTS_PASS_NOT_ANDROID_BUILD',
        'repository': 'TWRP-Test/android_system_core', 'commit': COMMIT,
        'baseline_sha256': {'init/selinux.cpp': SELINUX_SHA, 'init/Android.bp': BP_SHA},
        'candidate_selinux_sha256': digest(candidate.encode()),
        'patch_sha256': digest((ROOT / 'recovery-only-permissive.patch').read_bytes()),
        'patch_applies_to_pinned_baseline_exactly': True,
        'scope': 'Only RECOVERY builds override the existing IsEnforcing result at the existing security_setenforce site. Normal Android keeps original selector and fatal handling.',
        'build_configuration_assertions': {'selinux_in_libinit': True, 'libinit_recovery_defines_RECOVERY': True,
            'init_second_stage_recovery_defines_RECOVERY': True, 'normal_target_has_no_RECOVERY_define': True},
        'host_test_source': 'test_extracted_function.cpp (generated directly from candidate production function)',
        'tests': results, 'total_cases': 16, 'ASAN_UBSAN': 'PASS', 'LSAN_enabled': False,
        'limits': ['No Android init build, image integration or device test performed.',
                  'Host tests stub security_getenforce, IsEnforcing, security_setenforce and fatal logger boundaries.',
                  'Existing treatment of security_getenforce errors is unchanged and not broadened by this patch.',
                  'Full recovery image pins and native PID1 init/RC contracts need regeneration after a real build.',
                  'Keep shared bootconfig permissive until new recovery binary identity and behavior are verified.'],
    }
    (ROOT / 'SOURCE-CANDIDATE-REVIEW.json').write_text(json.dumps(review, indent=2) + '\n')
    print(json.dumps(review, indent=2))


if __name__ == '__main__':
    main()
