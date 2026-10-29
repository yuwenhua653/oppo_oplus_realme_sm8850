#!/usr/bin/env python3
"""Import only exact R96 runtime modules into a source-built myron recovery.

This does not emit a flashable image. The new recovery must subsequently be
paired with a PID1 built against its exact init/recovery/RC bytes.
"""
import argparse, ctypes, ctypes.util, hashlib, json, re, shlex, struct
import subprocess, tempfile
from pathlib import Path

VENDOR_SHA = '40c62b7f726b011c59149cb9c22ec24a60beafddf4f6ed702506de29ccd03eb3'
PAYLOADS = {'vendor_dlkm':'549207605ef4af68d0fac1b7aa4b1c28949a59670c56bdd3c8602e387f6fdfb1',
            'system_dlkm':'cb15ca845f4850b9ee843927690f2bf08bcdf5c24c4a2c2db04696055127ae8e'}
CONTRACT_SHA = 'eefac3d5d863ad0d5da6ece2b566cbebe098e82f7289a51378025cd2c80e3da9'
KERNEL = '6.12.81-android16-6-maybe-dirty-4k'
def need(v,m):
    if not v: raise ValueError(m)
def sha(b): return hashlib.sha256(b).hexdigest()
def cpio(raw):
    result={};at=0
    while True:
        need(raw[at:at+6]==b'070701','newc magic')
        h=[int(raw[at+6+i*8:at+14+i*8],16) for i in range(13)]
        need(h[11]>0 and at+110+h[11]<=len(raw),'name bounds')
        n=raw[at+110:at+110+h[11]-1].decode();start=(at+110+h[11]+3)&~3
        need(n not in result and start+h[6]<=len(raw),'unique bounded record')
        need(not n.startswith('/') and '..' not in Path(n).parts,'safe path')
        result[n]=raw[start:start+h[6]];at=(start+h[6]+3)&~3
        if n=='TRAILER!!!':break
    need(not any(raw[at:]),'cpio tail');return result
def unpack_vendor(path):
    b=Path(path).read_bytes();need(len(b)==100663296 and sha(b)==VENDOR_SHA,'exact R96 vendor_boot required')
    need(b[:8]==b'VNDRBOOT' and struct.unpack_from('<I',b,12)[0]==4096,'vendor header')
    n=struct.unpack_from('<I',b,24)[0];rd=b[4096:4096+n]
    need(rd[:4]==bytes.fromhex('02214c18'),'legacy lz4')
    lib=ctypes.CDLL(ctypes.util.find_library('lz4'))
    lib.LZ4_decompress_safe.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_int]
    lib.LZ4_decompress_safe.restype=ctypes.c_int
    at=4;raw=bytearray()
    while at<len(rd):
        n=struct.unpack_from('<I',rd,at)[0];at+=4;need(0<n<=8*1024*1024 and at+n<=len(rd),'lz4 bounds')
        src=ctypes.create_string_buffer(rd[at:at+n]);dst=ctypes.create_string_buffer(8*1024*1024)
        size=lib.LZ4_decompress_safe(src,dst,n,len(dst));need(size>0,'lz4 decode')
        raw+=dst.raw[:size];at+=n;need(len(raw)<256*1024*1024,'bounded ramdisk')
    return cpio(raw)
def command(argv):
    r=subprocess.run(argv,check=True,capture_output=True,timeout=60);return r.stdout
def info(path):
    s=command(['readelf','-p','.modinfo',str(path)]).decode()
    d=dict(re.findall(r'\]\s+(name|depends|vermagic)=(.*)',s))
    need(d.get('vermagic','').startswith(KERNEL+' '),'vermagic '+str(path))
    need(re.fullmatch('[a-zA-Z0-9_]+',d.get('name','')),'module name')
    return d
def build(vendor,out):
    records=unpack_vendor(vendor);out=Path(out);need(not out.exists(),'runtime output must be new')
    with tempfile.TemporaryDirectory(prefix='r97-import-') as tmp:
        t=Path(tmp);files={}
        for k,h in PAYLOADS.items():
            blob=records['r32-payload/'+k+'.img'];need(sha(blob)==h,'payload hash '+k)
            image=t/(k+'.img');image.write_bytes(blob)
            dest=t/k;dest.mkdir()
            command(['debugfs','-R',f'rdump / {dest}',str(image)])
            for p in dest.rglob('*.ko'):files['/'+k+'/'+p.relative_to(dest).as_posix()]=p
        cb=(t/'vendor_dlkm/r32/r92-mca/module-set.json').read_bytes();need(sha(cb)==CONTRACT_SHA,'MCA contract')
        contract=json.loads(cb);need(contract['build_id']=='R94-MCA-TORCH-COMPAT-20261028-01','runtime ID preserved')
        rows={r['name']:r for r in contract['baseline']+contract['additions']};need(len(rows)==295,'295 frozen modules')
        meta={}
        for n,r in rows.items():
            b=files[r['path']].read_bytes();need(len(b)==r['bytes'] and sha(b)==r['sha256'],'module pin '+n)
            meta[n]=info(files[r['path']]);need(meta[n]['name']==n,'module contract name')
        first=[]
        for line in records['lib/modules/modules.load'].decode().splitlines():
            line=line.strip()
            if not line or line.startswith('#'):continue
            b=records['lib/modules/'+line];n=Path(line).stem.replace('-','_')
            need(n in rows and sha(b)==rows[n]['sha256'],'firststage matches runtime '+n);first.append(n)
        need(len(first)==len(set(first))==142,'firststage count from exact R96 image')
        loads=[]
        for line in (t/'vendor_dlkm/r32/load-modules.sh').read_text().splitlines():
            if line.strip().startswith('load_one '):loads.append(shlex.split(line.strip())[1:])
        arguments={x[0]:x[3:] for x in loads}
        normal_order=list(dict.fromkeys(first+[x[0] for x in loads if x[0] not in first]))
        # tfa98xx has a separate conditional firmware-gated insertion; machine
        # has two alternative argument sets. Neither belongs in recovery.
        need(set(normal_order)=={r['name'] for r in contract['baseline']}-{'tfa98xx_dlkm'},'normal order inventory')
        order=normal_order+[r['name'] for r in contract['additions']]
        def closure(seeds):
            found=set()
            def add(n):
                need(n in rows,'dependency absent '+n)
                if n in found:return
                found.add(n)
                for dep in filter(None,meta[n].get('depends','').split(',')):add(dep.replace('-','_'))
            for n in seeds:add(n)
            return found
        ui=closure(['msm_drm','focaltech_myron','spi_msm_geni','qti_fixed_regulator','nvmem_qfprom'])
        # Include the same ADSP transport group as the verified Android route.
        hardware=closure(['qcom_hv_haptics','qti_battery_charger','adsp_loader_dlkm','qrtr_smd',
            'glink_pkt','frpc_adsprpc','snd_event_dlkm','q6_pdr_dlkm','q6_notifier_dlkm',
            'gpr_dlkm','spf_core_dlkm']+[r['name'] for r in contract['additions']])
        selected=ui|hardware;loaded=set(first);plan=[]
        for n in order:
            if n not in selected:continue
            deps={d.replace('-','_') for d in filter(None,meta[n].get('depends','').split(','))}
            need(deps<=loaded,'dependency order '+n);loaded.add(n)
            r=dict(rows[n]);r.update(file=Path(r['path']).name,firststage=n in first,phase='ui' if n in ui else 'hardware',args=arguments.get(n,[]))
            plan.append(r)
        need({r['name'] for r in plan}==selected,'complete closure')
        need(all(order.index(a)<order.index(b) for a,b in contract['semantic_before']),'MCA semantic order')
        out.mkdir(parents=True);(out/'modules').mkdir()
        for r in plan:(out/'modules'/r['file']).write_bytes(files[r['path']].read_bytes())
        (out/'allowed-live.txt').write_text('\n'.join(sorted(set(first)|selected))+'\n')
        (out/'firststage.txt').write_text('\n'.join(first)+'\n')
        (out/'modules.sha256').write_text(''.join(r['sha256']+'  modules/'+r['file']+'\n' for r in plan))
        for phase in ['ui','hardware']:
            (out/(phase+'.list')).write_text(''.join('|'.join([r['name'],r['file'],' '.join(r['args'])])+'\n' for r in plan if r['phase']==phase and not r['firststage']))
        result={'schema':1,'vendor_boot_sha256':VENDOR_SHA,'runtime_identity':contract['build_id'],
                'kernel':KERNEL,'modules':plan,'firststage':first,'MCA_count':46,
                'physical_tested':False,'firmware_action':'identity-checked ADSP start once; no SSR/stop/retry'}
        (out/'module-plan.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'selected':len(plan),'ui_new':sum(r['phase']=='ui' and not r['firststage'] for r in plan),'hardware_new':sum(r['phase']=='hardware' and not r['firststage'] for r in plan)}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--vendor-boot',required=True);p.add_argument('--out',required=True);a=p.parse_args();build(a.vendor_boot,a.out)
