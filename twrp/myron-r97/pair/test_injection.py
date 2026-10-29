#!/usr/bin/env python3
"""End-to-end assembly regression using an explicitly synthetic CI fixture.

Temporary images are deleted. This test cannot deliver a compiled R97 image.
"""
import argparse, importlib, json, sys, tempfile
from pathlib import Path
from read_candidate import need, read_image, verify_candidate, verify_entries
from prepare_recovery import prepare
from build_vendor_boot import build

def test(a):
    sys.path.insert(0,str(Path(a.image_tools).resolve()))
    im=importlib.import_module('build_images')
    codec=im.LegacyLz4()
    image,entries=read_image(a.r95_recovery)
    h=im.android_header(image,False);raw=codec.decompress(image[4096:4096+h['ramdisk_bytes']])
    source=Path(a.project)
    rc=(source/'reference/init.rc').read_text()
    rc='import /init.recovery.r97.rc\nimport /system/etc/init\nimport /vendor/etc/init\nimport /odm/etc/init\n'+rc
    for name in ['recovery','charger']:
        s='service '+name+' /system/bin/'+name+'\n';need(rc.count(s)==1,'core RC anchor');rc=rc.replace(s,s+'    disabled\n')
    # One trailing ELF padding byte solely creates a distinct binary-size test
    # branch. This is explicitly not compilation and never leaves the temp dir.
    replacements={'system/etc/init/hw/init.rc':rc.encode(),
                  'system/bin/recovery':entries['system/bin/recovery']['data']+b'\0'}
    adds=[('R97-COMPILE-ONLY-NOT-FLASHABLE',b'SYNTHETIC TEST ONLY\n',0o100644),
          ('r97-runtime',b'',0o40755),
          ('r97-runtime/module-plan.json',b'{"compile_only":true}\n',0o100644)]
    for p in sorted((source/'overlay/recovery/root').rglob('*')):
        n=p.relative_to(source/'overlay/recovery/root').as_posix()
        if p.is_file():adds.append((n,p.read_bytes(),0o100755 if p.suffix=='.sh' else 0o100644))
    cpio,_,_,_=im.rebuild_cpio(raw,lambda _:False,replacements,adds)
    payload,_=im.recovery_payload(image,codec.compress(cpio,9))
    candidate,_=im.append_avb(payload,image,'recovery',None)
    with tempfile.TemporaryDirectory(prefix='r97-SYNTHETIC-NOT-FLASHABLE-') as d:
        root=Path(d);ci=root/'synthetic-ci.img';ci.write_bytes(candidate)
        try:verify_candidate(ci)
        except ValueError as e:need('source-only' in str(e),'candidate rejected for marker')
        else:raise AssertionError('unassembled source-only candidate accepted')
        rec=root/'synthetic-recovery.img'
        prepared=prepare(ci,a.runtime,a.image_tools,rec)
        _,after=read_image(rec)
        need('R97-COMPILE-ONLY-NOT-FLASHABLE' not in after,'marker removed')
        need(prepared['module_count']==126,'126 modules exact')
        negative=[]
        for path in ['r97-runtime/'+n for n in ['ui.list','hardware.list','allowed-live.txt',
                     'firststage.txt','modules.sha256','common.sh','load-ui.sh','load-hardware.sh',
                     'start-adsp.sh','wait-battery.sh']]+['init.recovery.r97.rc']:
            bad=dict(after);bad[path]={**after[path],'data':after[path]['data']+b'corruption'}
            try:verify_entries(bad,prepared['image'])
            except ValueError:negative.append(path)
            else:raise AssertionError('corrupt control/script accepted: '+path)
        bad=dict(after);bad['init']={**after['init'],'data':b'/system/bin/unreviewed-init'}
        try:verify_entries(bad,prepared['image'])
        except ValueError:negative.append('init symlink')
        else:raise AssertionError('unknown init link accepted')
        bad=dict(after);bad['r97-runtime/extra.sh']={'mode':0o100755,'data':b'exit 0\n'}
        try:verify_entries(bad,prepared['image'])
        except ValueError:negative.append('extra runtime file')
        else:raise AssertionError('unexpected runtime accepted')
        paired=build(a.r96_vendor,rec,a.baseline_native,a.toolchain,a.image_tools,
                     a.independent_reader,root/'synthetic-pair')
        need(paired['only_vendor_entry_changed']=='r36-init','sole PID1 replacement')
        return {'status':'PASS_SYNTHETIC_ASSEMBLY_REGRESSION_ONLY',
                'real_R97_compilation':False,'flashable_output_produced':False,
                'source_only_marker_rejected':True,'marker_removed_after_injection':True,
                '126_private_module_bytes_verified':True,'independent_record_readback':True,
                'corrupt_control_script_link_inventory_rejected':negative,
                'deterministic_native_and_vendor_build':True,
                'normal_R96_contract_preserved':True,'native_tests':paired['native_tests']}

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ['r95-recovery','r96-vendor','baseline-native','runtime','project','toolchain','image-tools','independent-reader']:
        p.add_argument('--'+n,required=True)
    print(json.dumps(test(p.parse_args()),indent=2))
