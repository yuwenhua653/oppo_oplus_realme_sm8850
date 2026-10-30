#!/usr/bin/env python3
"""Collect static AArch64 helpers; source builds are not runtime qualification."""
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
from pathlib import Path

def identity(p):
    return {'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}

def static_arm64(p):
    data=p.read_bytes()
    if len(data)<64 or data[:6]!=b'\x7fELF\x02\x01' or struct.unpack_from('<H',data,18)[0]!=183:
        raise ValueError('not ELF64 AArch64')
    if struct.unpack_from('<H',data,16)[0] not in (2,3):
        raise ValueError('not executable ELF')
    off=struct.unpack_from('<Q',data,32)[0];size,count=struct.unpack_from('<HH',data,54)
    if size!=56 or off+size*count>len(data):raise ValueError('program headers')
    stacks=0;executable_loads=0
    for i in range(count):
        typ,flags,pos,_,_,length,mem,align=struct.unpack_from('<IIQQQQQQ',data,off+i*size)
        if pos+length>len(data):raise ValueError('segment geometry')
        if typ==3:raise ValueError('dynamic interpreter')
        if typ==1 and (flags&3==3 or length>mem):raise ValueError('unsafe load segment')
        if typ==1 and flags&1 and length:executable_loads+=1
        if typ==0x6474e551:
            stacks+=1
            if flags&1:raise ValueError('executable stack')
    if stacks!=1:raise ValueError('GNU stack absent or duplicated')
    if not executable_loads:raise ValueError('nonempty executable load segment required')
    dynamic=subprocess.check_output(['readelf','-dW',str(p)],text=True)
    if re.search(r'\((NEEDED|RPATH|RUNPATH)\)',dynamic):raise ValueError('unexpected dynamic dependency')
    return {'aarch64':True,'static':True,'no_interpreter':True,'nonexecutable_stack':True,'no_writable_executable_load':True}

def main():
    root=Path(os.environ['RUNNER_TEMP']);product=root/'r97-aosp/out/target/product/sm8850'
    deliver=root/'r99-readiness-deliver';deliver.mkdir(exist_ok=False)
    evidence=root/'r99-evidence';rows=[]
    for name,location in [('r99_readiness_broker','system/bin'),('r99_readiness_client','vendor/bin')]:
        original=product/location/name
        if not original.is_file() or original.is_symlink():raise ValueError('missing native output '+name)
        target=deliver/name;shutil.copyfile(original,target)
        rows.append({'name':name,'build_output':location+'/'+name,**identity(target),'elf':static_arm64(target)})
        with (evidence/(name+'-readelf.txt')).open('w') as f:
            subprocess.run(['readelf','-hW','-lW','-dW','-nW','-Ws',str(target)],stdout=f,check=True)
    source=Path(__file__).resolve().parent/'readiness/SOURCE-FILES.json'
    shutil.copyfile(source,deliver/'SOURCE-FILES.json')
    result={'status':'NATIVE_COMPILE_ONLY_RUNTIME_INTEGRATION_REQUIRED','outputs':rows,
            'image_built':False,'service_installed':False,'device_tested':False,
            'runtime_placement_qualified':False,'property_contexts_installed':False}
    (deliver/'BUILD-RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
    shutil.copyfile(deliver/'BUILD-RESULT.json',evidence/'READINESS-BUILD-RESULT.json')
    (deliver/'README.txt').write_text('Static native build outputs only. Do not push or execute on a phone.\n'
        'Core-owned placement, SELinux/property contexts, init service and bounded client integration are not supplied by this compiler artifact.\n')
    print(json.dumps(result,indent=2))

if __name__ == '__main__':
    main()
