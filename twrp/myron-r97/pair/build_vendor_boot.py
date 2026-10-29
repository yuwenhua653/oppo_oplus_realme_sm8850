#!/usr/bin/env python3
"""Compile matched PID1; replace only r36-init in exact R96 vendor_boot."""
import argparse, importlib, json, os, struct, subprocess, sys
from pathlib import Path
from generate_native import generate
from read_candidate import need, pin, verify_candidate
from test_pair import C_TEST

VENDOR_PIN = {'bytes':100663296,'sha256':'40c62b7f726b011c59149cb9c22ec24a60beafddf4f6ed702506de29ccd03eb3'}

def build(vendor, recovery, baseline, toolchain, image_tools, independent_reader, out):
    out = Path(out);need(not out.exists(), 'output already exists');out.mkdir(parents=True)
    reviewed = verify_candidate(recovery)
    original = Path(vendor).read_bytes();need(pin(original)==VENDOR_PIN,'exact stable R96 vendor_boot')
    native=out/'native';generate(baseline,native,reviewed)
    tc=json.loads(Path(toolchain).read_text());env={**os.environ,**tc['env_overrides']}
    bins=[]
    for name in ['r36-init','r36-init-repeat']:
        executable=native/name
        subprocess.run(tc['compile_argv']+['-o',str(executable),str(native/'r36_init.c')],env=env,check=True)
        subprocess.run(tc['strip_argv']+[str(executable)],env=env,check=True)
        bins.append(executable.read_bytes())
    need(bins[0]==bins[1],'deterministic PID1 compilation')
    pid=bins[0]
    need(pid[:6]==b'\x7fELF\x02\x01' and struct.unpack_from('<H',pid,18)[0]==183,'AArch64 ELF64 PID1')
    phoff=struct.unpack_from('<Q',pid,32)[0];entsize,count=struct.unpack_from('<HH',pid,54)
    need(entsize==56 and phoff+entsize*count<=len(pid),'ELF program header geometry')
    need(all(struct.unpack_from('<I',pid,phoff+i*entsize)[0]!=3 for i in range(count)),'PID1 must be static')
    # Tests use the final generated source/header, with the original R96 suite.
    flags=['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function',
           '-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie']
    test_env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0:abort_on_error=1','UBSAN_OPTIONS':'halt_on_error=1'}
    tests=[]
    (native/'test_r97_bundle.c').write_text(C_TEST)
    for source in [native/'test_r97_bundle.c',native/'test_rc_selection.c',native/'tests/test_native.c']:
        exe=source.with_suffix('');subprocess.run(flags+[str(source),'-o',str(exe)],check=True)
        r=subprocess.run([str(exe)],env=test_env,capture_output=True,text=True,check=True)
        tests.append({'name':source.name,'output':r.stdout+r.stderr})
    sys.path.insert(0,str(Path(image_tools).resolve()));im=importlib.import_module('build_images')
    sys.path.insert(0,str(Path(independent_reader).resolve()));reader=importlib.import_module('read_cpio')
    sections,_=im.vendor_sections(original);codec=im.LegacyLz4()
    raw=codec.decompress(sections['ramdisk'])
    cpio,_,_,changes=im.rebuild_cpio(raw,lambda _:False,{'r36-init':pid},[])
    need(len(changes)==1 and changes[0]['name']=='r36-init','one native entry replacement')
    result,avb=im.append_avb(im.vendor_payload(original,codec.compress(cpio,9),sections),original,'vendor_boot',None)
    path=out/'vendor_boot_r97.img';path.write_bytes(result)
    os.link(path,out/'vendor_boot.img')
    need(len(result)==100663296,'vendor partition geometry')
    rebuilt,_=im.append_avb(im.vendor_payload(original,codec.compress(cpio,9),sections),original,'vendor_boot',None)
    need(rebuilt==result,'deterministic vendor_boot encoding')
    # Independent CPIO reader compares entire raw records, not just file hashes.
    _,old=reader.extract(Path(vendor));_,new=reader.extract(path)
    need(list(old)==list(new),'same vendor CPIO inventory/order')
    need([n for n in old if old[n]['record']!=new[n]['record']]==['r36-init'],'all unchanged records exact')
    need(new['r36-init']['data']==pid,'actual compiled PID1 embedded')
    after,_=im.vendor_sections(result)
    need(after['dtb']==sections['dtb'] and after['bootconfig']==sections['bootconfig'] and
         after['table'][4:]==sections['table'][4:],'DTB bootconfig and table identity')
    header=bytearray(result[:4096]);header[24:28]=original[24:28]
    need(header==original[:4096],'vendor header preserved except ramdisk size')
    check=subprocess.run([sys.executable,str(Path(image_tools)/'avbtool.py'),'verify_image','--image',str(path)],capture_output=True,text=True,check=True)
    report={'status':'STATIC_PAIR_VERIFIED_NOT_DEVICE_TESTED','vendor_boot':pin(result),
            'recovery':reviewed,'pid1':pin(pid),'normal_contract_unchanged':True,
            'only_vendor_entry_changed':'r36-init','native_tests':tests,'AVB':avb,
            'AVB_verification':check.stdout+check.stderr,'device_tested':False}
    (out/'PAIR-REVIEW.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ['vendor','recovery','baseline','toolchain','image-tools','independent-reader','out']:
        p.add_argument('--'+name,required=True)
    a=p.parse_args()
    print(json.dumps(build(a.vendor,a.recovery,a.baseline,a.toolchain,a.image_tools,a.independent_reader,a.out),indent=2))
