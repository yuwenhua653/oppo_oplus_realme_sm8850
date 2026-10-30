#!/usr/bin/env python3
"""Exercise manifest drift rejection and ELF guard failure paths without a phone."""
import importlib.util
import json
import shutil
import struct
import tempfile
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent

def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-','_'), HERE/(name+'.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def main():
    pins, elf, native = load('validate-inputs'), load('inspect-init'), load('collect-readiness')
    assert len(pins.manifest()) == 396
    cases = 1
    with tempfile.TemporaryDirectory(prefix='r99-controls-') as tmp:
        root = Path(tmp)
        for name in ('source-lock.json', 'resolved-manifest.xml'):
            shutil.copyfile(HERE/name, root/name)
        (root/'resolved-manifest.xml').write_bytes((root/'resolved-manifest.xml').read_bytes()+b'\n')
        with patch.object(pins, 'ROOT', root):
            try: pins.manifest()
            except AssertionError: cases += 1
            else: raise AssertionError('modified source snapshot accepted')
        # A minimal ELF header/segment fixture; readelf is the mocked platform
        # boundary, while the production header validation remains unchanged.
        data = bytearray(512)
        data[:6] = b'\x7fELF\x02\x01'
        struct.pack_into('<HH',data,16,3,183)
        struct.pack_into('<Q',data,32,64)
        struct.pack_into('<HH',data,54,56,3)
        struct.pack_into('<IIQQQQQQ',data,64,1,5,0,0,0,len(data),len(data),4096)
        interp=b'/system/bin/linker64\0'
        struct.pack_into('<IIQQQQQQ',data,120,3,4,256,0,0,len(interp),len(interp),1)
        struct.pack_into('<IIQQQQQQ',data,176,0x6474e551,6,0,0,0,0,0,16)
        data[256:256+len(interp)] = interp
        binary = root/'init-fixture'
        needed='\n'.join(' 0x1 (NEEDED) Shared library: ['+x+']' for x in elf.EXPECTED_NEEDED)
        with patch.object(elf.subprocess, 'check_output', return_value=needed):
            binary.write_bytes(data)
            assert elf.elf_info(binary)['nonexecutable_stack']
            cases += 1
            mutations = [('machine',18,'<H',62), ('wx',68,'<I',7),
                         ('no-stack',176,'<I',0), ('exec-stack',180,'<I',7),
                         ('oversize-load',104,'<Q',len(data)-1),
                         ('bad-ph-size',54,'<H',55), ('no-load',64,'<I',0),
                         ('no-executable-load',68,'<I',4)]
            for name,offset,fmt,value in mutations:
                modified=bytearray(data); struct.pack_into(fmt,modified,offset,value)
                binary.write_bytes(modified)
                try: elf.elf_info(binary)
                except ValueError: cases += 1
                else: raise AssertionError('accepted invalid ELF '+name)
        binary.write_bytes(data)
        with patch.object(elf.subprocess, 'check_output', return_value=needed+'\n (RUNPATH) [/unexpected]'):
            try: elf.elf_info(binary)
            except ValueError: cases += 1
            else: raise AssertionError('accepted new library search path')
        static_data=bytearray(data);struct.pack_into('<I',static_data,120,0)
        with patch.object(native.subprocess, 'check_output', return_value=''):
            binary.write_bytes(static_data)
            assert native.static_arm64(binary)['static']
            cases += 1
            for name,offset,value in [('no-load',64,0),('no-executable-load',68,4)]:
                modified=bytearray(static_data);struct.pack_into('<I',modified,offset,value)
                binary.write_bytes(modified)
                try: native.static_arm64(binary)
                except ValueError: cases += 1
                else: raise AssertionError('accepted invalid static ELF '+name)
    print(json.dumps({'status':'PASS','manifest_and_elf_cases':cases,'real_ELF_executed':False}))

if __name__ == '__main__':
    main()
