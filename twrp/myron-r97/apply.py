#!/usr/bin/env python3
"""Apply the reviewed source changes to exact upstream inputs, before building."""
import argparse, hashlib, json, shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent
def need(v,m):
    if not v:raise ValueError(m)
def blob(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def patch(device,recovery,runtime):
    device=Path(device);recovery=Path(recovery);runtime=Path(runtime)
    lock=json.loads((HERE/'source-lock.json').read_text());pins=json.loads((HERE/'upstream-pins.json').read_text())
    # Validate everything before modifying the first source file.
    for n,h in pins.items():need(blob((device/n).read_bytes())==h,'upstream changed: '+n)
    need(blob((recovery/'etc/init.rc').read_bytes())==lock['recovery_init_blob'],'TWRP init changed')
    need(blob((recovery/'twrpminui/events.cpp').read_bytes())==lock['recovery_events_blob'],'TWRP haptics code changed')
    plan_bytes=(runtime/'module-plan.json').read_bytes()
    need(hashlib.sha256(plan_bytes).hexdigest()==lock['module_plan_sha256'],'exact reviewed module plan')
    plan=json.loads(plan_bytes)
    need(plan['runtime_identity']==lock['runtime_identity'] and plan['MCA_count']==46,'runtime contract')
    for row in plan['modules']:
        b=(runtime/'modules'/row['file']).read_bytes()
        need(len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256'],'runtime bytes '+row['file'])
    controls={
        'firststage.txt':'\n'.join(plan['firststage'])+'\n',
        'allowed-live.txt':'\n'.join(sorted(set(plan['firststage'])|{r['name'] for r in plan['modules']}))+'\n',
        'modules.sha256':''.join(r['sha256']+'  modules/'+r['file']+'\n' for r in plan['modules']),
    }
    for phase in ['ui','hardware']:
        controls[phase+'.list']=''.join('|'.join([r['name'],r['file'],' '.join(r['args'])])+'\n' for r in plan['modules'] if r['phase']==phase and not r['firststage'])
    for n,s in controls.items():need((runtime/n).read_text()==s,'runtime control file '+n)
    inventory={'module-plan.json',*controls}|{'modules/'+r['file'] for r in plan['modules']}
    need(not any(p.is_symlink() for p in runtime.rglob('*')),'no input symlinks')
    need({p.relative_to(runtime).as_posix() for p in runtime.rglob('*') if p.is_file()}==inventory,'runtime file inventory')
    changes={}
    board=(device/'BoardConfig.mk').read_text()
    board=board.replace('TW_SUPPORT_INPUT_AIDL_HAPTICS := true','TW_SUPPORT_INPUT_AIDL_HAPTICS := false')
    board=board.replace('TW_SUPPORT_INPUT_AIDL_HAPTICS_FIX_OFF := true','TW_SUPPORT_INPUT_AIDL_HAPTICS_FIX_OFF := false')
    board='\n'.join('TW_LOAD_VENDOR_MODULES := ""' if s.startswith('TW_LOAD_VENDOR_MODULES := ') else s for s in board.splitlines())+'\n'
    board+='''
# R97/myron: use the FF implementation in the pinned TWRP core and only the
# byte-verified R96 module closure. There is no fallback to stock OEM modules.
ifeq ($(wildcard $(DEVICE_PATH)/recovery/root/r97-runtime/module-plan.json),)
$(error Run the R97 prepare_runtime.py + apply.py steps before building)
endif
'''
    changes['BoardConfig.mk']=board
    q=(device/'recovery/root/init.recovery.qcom.rc').read_text()
    a=q.index('on property:twrp.modules.loaded=true\n');b=q.index('on property:twrp.adsp.ready=true',a)
    q=q[:a]+'''# R97: module loading and ADSP startup are independently supervised.
# Do not issue the stock boot_adsp/ssr write on this OSS runtime.
on fs
    mkdir /firmware 0755 root root
    wait /dev/block/bootdevice/by-name/modem${ro.boot.slot_suffix} 10
    mount vfat /dev/block/bootdevice/by-name/modem${ro.boot.slot_suffix} /firmware ro

'''+q[b:]
    q=q.replace('    start vendor.health-default\n','')
    a=q.index('on property:twrp.variant.files_copied=1\n');b=q.index('on property:twrp.variant.files_copied=1 &&',a)
    q=q[:a]+'# Direct input FF and focaltech_myron replace the OEM haptics/touch HAL path.\n\n'+q[b:]
    a=q.index('service vendor.wait-adsp ');q=q[:a]
    changes['recovery/root/init.recovery.qcom.rc']=q
    # Both health processes are disabled until the real battery node is valid;
    # the charger UI is not started alongside the interactive recovery UI.
    h=(device/'recovery/root/vendor/etc/init/android.hardware.health-service.qti.rc').read_text()
    h='\n'.join(s+'\n    disabled' if s.startswith('service ') else s for s in h.splitlines())+'\n'
    # Upstream has two seclabel options for vendor.charger: retain recovery only.
    h=h.replace('    seclabel u:r:charger_vendor:s0\n','')
    changes['recovery/root/vendor/etc/init/android.hardware.health-service.qti.rc']=h
    changes['recovery/root/odm/etc/init/vendor.xiaomi.hardware.vibratorfeature.service.rc']='# R97 uses kernel input FF through TWRP; no OEM vibrator service or calibration writes.\n'
    v=(device/'recovery/root/odm/bin/variant-script.sh').read_text()
    v=v.replace('variant=$(getprop ro.boot.hardware.sku)', 'variant=$(getprop ro.boot.hardware.sku)\n[ "$variant" = myron ] || exit 1')
    v=v.replace('echo "$model" >/config/usb_gadget/g1/strings/0x409/product', 'if [ -w /config/usb_gadget/g1/strings/0x409/product ]; then\n    echo "$model" >/config/usb_gadget/g1/strings/0x409/product\nfi')
    changes['recovery/root/odm/bin/variant-script.sh']=v
    changes['recovery/root/vendor/bin/wait-adsp-ready.sh']='# Replaced by /r97-runtime/start-adsp.sh; no fixed remoteproc index.\nexit 1\n'
    pre=(device/'prebuilt/Android.mk').read_text()
    pre=pre.replace('include $(BUILD_PHONY_PACKAGE)', '''    LOCAL_POST_INSTALL_CMD += \\
        test -s $(LOCAL_PATH)/../recovery/root/r97-runtime/module-plan.json && \\
        cp -a $(LOCAL_PATH)/../recovery/root/r97-runtime $(TARGET_RECOVERY_ROOT_OUT)/;
include $(BUILD_PHONY_PACKAGE)''')
    changes['prebuilt/Android.mk']=pre
    init=(recovery/'etc/init.rc').read_text()
    init='import /init.recovery.r97.rc\nimport /system/etc/init\nimport /vendor/etc/init\nimport /odm/etc/init\n'+init
    for name in ['recovery','charger']:
        needle='service '+name+' /system/bin/'+name+'\n';need(init.count(needle)==1,'one '+name)
        init=init.replace(needle,needle+'    disabled\n')
    for n,s in changes.items():(device/n).write_text(s)
    shutil.copytree(HERE/'overlay',device,dirs_exist_ok=True)
    shutil.copytree(runtime,device/'recovery/root/r97-runtime',dirs_exist_ok=True)
    # OEM lazy vibrator manifest must not advertise an unstarted incompatible HAL.
    (device/'recovery/root/odm/etc/vintf/manifest/vendor.xiaomi.hardware.vibratorfeature.service.xml').unlink(missing_ok=True)
    (recovery/'etc/init.rc').write_text(init)
    result={'source_lock':lock,'device_changed':sorted(changes),'core_changed':['etc/init.rc'],
            'normal_android_changes':[],'release_allowed':False,
            'next_gate':'Full TWRP build, exact PID1 pairing and image readback required before flashing'}
    (device/'R97-SOURCE-REVIEW.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--device',required=True);p.add_argument('--recovery',required=True);p.add_argument('--runtime',required=True)
    a=p.parse_args();patch(a.device,a.recovery,a.runtime)
