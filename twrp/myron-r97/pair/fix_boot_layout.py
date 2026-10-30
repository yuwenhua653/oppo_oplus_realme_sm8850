#!/usr/bin/env python3
"""Repair only the proven R97 vendor_dlkm/etc layout conflict; keep all pins."""
import argparse,json,sys,subprocess
from pathlib import Path
from read_candidate import need,pin,read_image,verify_candidate,check_boot_layout
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'image-tools'))
import build_images as im
import read_cpio

def fix(source,out,vendor):
    source,out,vendor=Path(source),Path(out),Path(vendor)
    original,before=read_image(source)
    need(pin(original)['sha256']=='a6c948213c352690dac05b12ea7aee4b55566d75d7a198be4403e5410f16dd01','exact released R97 input')
    need(pin(vendor.read_bytes())['sha256']=='333bdc24a41e2746de9303c15ce9ac86d112fd383587866e82b4c286e09e2cdc','exact unchanged R97 vendor_boot')
    removals=check_boot_layout(before,allow_known_vendor_link=True)
    need(removals=={'vendor_dlkm/etc'},'one proven conflict')
    need(not out.exists(),'output already exists')
    codec=im.LegacyLz4();h=im.android_header(original,False)
    raw=codec.decompress(original[4096:4096+h['ramdisk_bytes']])
    cpio,_,_,changes=im.rebuild_cpio(raw,lambda e:e['name'] in removals,{},[])
    need(len(changes)==1 and changes[0]['action']=='removed','only remove one record')
    compressed=codec.compress(cpio,9)
    payload,_=im.recovery_payload(original,compressed)
    result,avb=im.append_avb(payload,original,'recovery',None)
    need(len(result)==len(original)==104857600,'same recovery partition size')
    repeat,_=im.append_avb(im.recovery_payload(original,codec.compress(cpio,9))[0],original,'recovery',None)
    need(result==repeat,'deterministic image assembly')
    out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(result)
    reviewed=verify_candidate(out)
    _,old=read_cpio.extract(source);_,new=read_cpio.extract(out)
    need(list(new)==[n for n in old if n not in removals],'same inventory/order except one removal')
    need(all(old[n]['record']==new[n]['record'] for n in new),'all retained raw CPIO records unchanged')
    _,after=read_image(out)
    for n in reviewed['pins']:need(before[n]==after[n],'existing PID1 pin bytes preserved: '+n)
    alias=out.parent/'recovery.img'
    need(not alias.exists(),'AVB alias exists');alias.hardlink_to(out)
    av=subprocess.run([sys.executable,str(HERE/'image-tools/avbtool.py'),'verify_image','--image',str(out)],text=True,capture_output=True,check=True)
    report={'status':'PASS_R97_FIX1_STATIC_NOT_DEVICE_TESTED','original_recovery':pin(original),'recovery':pin(result),
            'vendor_boot':pin(vendor.read_bytes()),'vendor_boot_unchanged':True,'removed_records':sorted(removals),
            'all_retained_raw_records_unchanged':True,'all_recovery_pins_unchanged':True,
            'early_boot_empty_directories':['system_dlkm','vendor_dlkm'],'candidate_validation':reviewed,
            'AVB':avb,'AVB_verify':av.stdout+av.stderr,'device_tested':False}
    out.with_suffix('.review.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--out',required=True);p.add_argument('--vendor',required=True)
    a=p.parse_args();print(json.dumps(fix(a.source,a.out,a.vendor),indent=2))
