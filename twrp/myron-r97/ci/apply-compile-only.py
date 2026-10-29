#!/usr/bin/env python3
"""Compile public TWRP sources without transferring private module bytes to CI.

Separate from apply.py: its real-byte validation remains unchanged and must
be used for local assembly. This output is missing its operational runtime.
"""
import argparse, hashlib, json, pathlib, shutil, subprocess, tempfile

HERE = pathlib.Path(__file__).resolve().parent.parent
PATCH_BLOB = '787cefdb9843873872b4c9488885ed744a4c64ad'
MARKER = 'R97-COMPILE-ONLY-NOT-FLASHABLE'

def blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()

def apply(root):
    root = pathlib.Path(root).resolve()
    device = root / 'device/xiaomi/sm8850'
    rec = root / 'bootable/recovery'
    lock = json.loads((HERE / 'source-lock.json').read_text())
    pins = json.loads((HERE / 'upstream-pins.json').read_text())
    for name, expected in pins.items():
        if blob((device / name).read_bytes()) != expected:
            raise ValueError('Changed upstream: ' + name)
    for name, key in [('etc/init.rc', 'recovery_init_blob'),
                      ('twrpminui/events.cpp', 'recovery_events_blob')]:
        if blob((rec / name).read_bytes()) != lock[key]:
            raise ValueError('Changed TWRP input: ' + name)
    patch = HERE / 'REVIEW.patch'
    if blob(patch.read_bytes()) != PATCH_BLOB:
        raise ValueError('Changed reviewed source patch')
    subprocess.run(['git', 'apply', '--check', str(patch)], cwd=root, check=True)
    subprocess.run(['git', 'apply', str(patch)], cwd=root, check=True)
    shutil.copytree(HERE / 'overlay', device, dirs_exist_ok=True)
    runtime = device / 'recovery/root/r97-runtime'
    # The makefile checks existence only. This is explicitly not the reviewed
    # module plan; production runtime validation still fails closed.
    (runtime / 'module-plan.json').write_text(json.dumps({
        'compile_only': True, 'flash_qualified': False,
        'private_runtime_included': False,
        'reason': 'Private module bytes must be injected locally after compilation.'
    }, indent=2) + '\n')
    (device / 'recovery/root' / MARKER).write_text(
        'Runtime modules absent. Local assembly and matched PID1 are mandatory.\n')
    (device / 'recovery/root/odm/etc/vintf/manifest/vendor.xiaomi.hardware.vibratorfeature.service.xml').unlink(missing_ok=True)
    (device / 'R97-COMPILE-ONLY.json').write_text(json.dumps({
        'source_lock': lock, 'compile_only': True, 'flash_qualified': False,
        'private_runtime_included': False, 'normal_android_changes': [],
        'postprocessing_required': ['inject exact runtime', 'remove compile-only marker',
                                    'create matching PID1/vendor_boot', 'independent readback']
    }, indent=2) + '\n')

def self_test():
    with tempfile.TemporaryDirectory(prefix='r97-compile-only-') as d:
        root = pathlib.Path(d)
        device = root / 'device/xiaomi/sm8850'
        rec = root / 'bootable/recovery'
        shutil.copytree(HERE / 'reference/device', device)
        (rec / 'etc').mkdir(parents=True)
        (rec / 'twrpminui').mkdir()
        shutil.copy2(HERE / 'reference/init.rc', rec / 'etc/init.rc')
        shutil.copy2(HERE / 'reference/events.cpp', rec / 'twrpminui/events.cpp')
        apply(root)
        plan = json.loads((device / 'recovery/root/r97-runtime/module-plan.json').read_text())
        assert plan['compile_only'] and not plan['private_runtime_included']
        assert (device / 'recovery/root' / MARKER).is_file()
        assert not list((device / 'recovery/root/r97-runtime').rglob('*.ko'))
        before = (rec / 'etc/init.rc').read_bytes()
        try:
            apply(root)
        except ValueError:
            pass
        else:
            raise AssertionError('Changed upstream was accepted')
        assert (rec / 'etc/init.rc').read_bytes() == before
    print('PASS compile-only patch, explicit missing-runtime marker and changed-source rejection')

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--source-root')
    p.add_argument('--self-test', action='store_true')
    a = p.parse_args()
    if a.self_test:
        self_test()
    elif a.source_root:
        apply(a.source_root)
    else:
        p.error('--source-root or --self-test required')
