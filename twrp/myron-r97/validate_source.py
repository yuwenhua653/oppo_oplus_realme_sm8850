#!/usr/bin/env python3
"""Host checks for the source overlay. This is not a full Android build."""
import argparse, hashlib, json, shutil, subprocess, tempfile
from pathlib import Path
from apply import patch
HERE=Path(__file__).resolve().parent
def validate(runtime=None):
    for p in (HERE/'overlay').rglob('*.sh'):subprocess.run(['sh','-n',str(p)],check=True)
    with tempfile.TemporaryDirectory(prefix='r97-source-') as d:
        root=Path(d);device=root/'device';rec=root/'recovery'
        shutil.copytree(HERE/'reference/device',device)
        (rec/'etc').mkdir(parents=True);(rec/'twrpminui').mkdir()
        shutil.copy2(HERE/'reference/init.rc',rec/'etc/init.rc')
        shutil.copy2(HERE/'reference/events.cpp',rec/'twrpminui/events.cpp')
        if runtime is None:
            # Public CI has no private runtime bytes. Check fail-closed behavior;
            # the real-byte application is separately run before packaging.
            bad=root/'bad-runtime';bad.mkdir()
            (bad/'module-plan.json').write_text('{}')
            before=(device/'BoardConfig.mk').read_bytes()
            try:patch(device,rec,bad)
            except ValueError:pass
            else:raise AssertionError('unqualified runtime was accepted')
            assert (device/'BoardConfig.mk').read_bytes()==before
            print('PASS upstream pins, shell syntax, invalid runtime rejected before mutation; real-byte application not run')
            return
        patch(device,rec,runtime)
        init=(rec/'etc/init.rc').read_text();qcom=(device/'recovery/root/init.recovery.qcom.rc').read_text()
        health=(device/'recovery/root/vendor/etc/init/android.hardware.health-service.qti.rc').read_text()
        assert 'service recovery /system/bin/recovery\n    disabled\n' in init
        assert 'service charger /system/bin/charger\n    disabled\n' in init
        assert 'boot_adsp/boot' not in qcom and 'write /sys/kernel/boot_adsp/ssr' not in qcom
        assert 'start vendor.health-default' not in qcom
        assert 'start odm.vibratorfeature-hal-service' not in qcom and 'start odm.touch_report' not in qcom
        assert health.count('    disabled\n')==2
        subprocess.run(['bash','-n',str(device/'recovery/root/odm/bin/variant-script.sh')],check=True)
        board=(device/'BoardConfig.mk').read_text()
        assert 'TW_SUPPORT_INPUT_AIDL_HAPTICS := false' in board
        assert 'TW_LOAD_VENDOR_MODULES := ""' in board
        # Make parses the actual BoardConfig; dummy runtime presence satisfies
        # the deliberate missing-input guard without an Android source checkout.
        makefile=root/'check.mk';makefile.write_text('DEVICE_PATH := '+str(device)+'\ninclude '+str(device/'BoardConfig.mk')+'\nall:\n\t@echo source-config-ok\n')
        subprocess.run(['make','-s','-f',str(makefile)],check=True)
        # Repeat application must fail before mutating already-modified sources.
        before=(rec/'etc/init.rc').read_bytes()
        try:patch(device,rec,runtime)
        except ValueError:pass
        else:raise AssertionError('changed upstream was not rejected')
        assert (rec/'etc/init.rc').read_bytes()==before
    print('PASS source application, upstream pins, init gates, Make and shell syntax')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--runtime');a=p.parse_args();validate(a.runtime)
