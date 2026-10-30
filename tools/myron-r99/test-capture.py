#!/usr/bin/env python3
"""Exercise capture to completion, with external ELF tools narrowly stubbed."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('r99_inspect_capture', HERE/'inspect-init.py')
inspect = importlib.util.module_from_spec(spec); spec.loader.exec_module(inspect)
PRODUCER = 'Android fixture based on r547379 clang version 20.0.0 (host test only)'

def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()

def commit(root):
    git(root,'init','-q'); git(root,'add','.')
    git(root,'-c','user.name=R99 host fixture','-c','user.email=r99-fixture@example.invalid','commit','-qm','test fixture')
    return git(root,'rev-parse','HEAD')

def fixture_elf():
    data = bytearray(1024); data[:6] = b'\x7fELF\x02\x01'
    struct.pack_into('<HH',data,16,3,183); struct.pack_into('<Q',data,32,64)
    struct.pack_into('<HH',data,54,56,3)
    struct.pack_into('<IIQQQQQQ',data,64,1,5,0,0,0,len(data),len(data),4096)
    interp=b'/system/bin/linker64\0'
    struct.pack_into('<IIQQQQQQ',data,120,3,4,256,0,0,len(interp),len(interp),1)
    struct.pack_into('<IIQQQQQQ',data,176,0x6474e551,6,0,0,0,0,0,16)
    data[256:256+len(interp)] = interp
    names=b'\0.shstrtab\0.text\0.comment\0'; data[300:300+len(names)]=names
    data[350:354]=b'TEXT'; comment=(PRODUCER+'\0').encode(); data[400:400+len(comment)]=comment
    struct.pack_into('<Q',data,40,700); struct.pack_into('<HHH',data,58,64,4,1)
    for i, (name,offset,length) in enumerate([(0,0,0),(1,300,len(names)),(11,350,4),(17,400,len(comment))]):
        struct.pack_into('<IIQQQQIIQQ',data,700+i*64,name,1,0,0,offset,length,0,0,1,0)
    return bytes(data)

def setup(root):
    source=root/'source'; controls=root/'controls'; controls.mkdir()
    core=source/'system/core'; init=core/'init'; init.mkdir(parents=True)
    for name in ('selinux.cpp','Android.bp'): shutil.copyfile(HERE/'selector/baseline'/name,init/name)
    lock=json.loads((HERE/'source-lock.json').read_text()); lock['system_core_commit']=commit(core)
    (controls/'source-lock.json').write_text(json.dumps(lock))
    soong=source/'build/soong'; config=soong/'cc/config/global.go'; config.parent.mkdir(parents=True)
    config.write_text('ClangDefaultBase = "prebuilts/clang/host"\nClangDefaultVersion = "clang-r547379"\n')
    soong_head=commit(soong)
    prebuilts=source/'prebuilts/clang/host/linux-x86'; selected=prebuilts/'clang-r547379/bin/clang'; selected.parent.mkdir(parents=True)
    selected.write_text('#!/bin/sh\nprintf "%s\\n" "'+PRODUCER+'"\n'); selected.chmod(0o755)
    legacy=prebuilts/'clang-3289846/bin/clang'; legacy.parent.mkdir(parents=True)
    legacy.write_text('#!/bin/sh\ntouch "'+str(root/'LEGACY-EXECUTED')+'"\nexit 127\n'); legacy.chmod(0o755)
    clang_head=commit(prebuilts)
    (controls/'resolved-manifest.xml').write_text('<manifest><project path="build/soong" revision="'+soong_head+'"/><project path="prebuilts/clang/host/linux-x86" revision="'+clang_head+'"/></manifest>')
    product=source/'out/target/product/sm8850'
    for path in ('recovery/root/system/bin/init','symbols/recovery/root/system/bin/init'):
        target=product/path; target.parent.mkdir(parents=True); target.write_bytes(fixture_elf())
    for name in inspect.EXPECTED_NEEDED:
        path=product/'recovery/root/system/lib64'/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(('HOST LIBRARY FIXTURE '+name).encode())
    return source, controls, selected

def main():
    cases=[]
    original_run=inspect.subprocess.run
    original_check_output=inspect.subprocess.check_output
    def run(args, **kwargs):
        name=Path(args[0]).name
        if name in ('readelf','aarch64-linux-gnu-objdump'):
            if 'stdout' in kwargs: kwargs['stdout'].write('HOST EXTERNAL TOOL FIXTURE\n')
            stdout='HOST EXTERNAL TOOL FIXTURE\n' if kwargs.get('text') else b'HOST EXTERNAL TOOL FIXTURE\n'
            return subprocess.CompletedProcess(args,0,stdout,'' if kwargs.get('text') else b'')
        return original_run(args,**kwargs)
    def output(args, **kwargs):
        if args[0]=='readelf': return '\n'.join(' (NEEDED) ['+name+']' for name in inspect.EXPECTED_NEEDED)
        return original_check_output(args,**kwargs)
    with tempfile.TemporaryDirectory(prefix='r99-capture-') as temp:
        root=Path(temp); source,controls,selected=setup(root)
        evidence=root/'evidence'; deliver=root/'deliver'
        with patch.object(inspect,'HERE',controls), patch.object(inspect.subprocess,'run',side_effect=run), patch.object(inspect.subprocess,'check_output',side_effect=output), patch.object(inspect.shutil,'which',side_effect=lambda name:'/host-fixture/'+name), patch.dict(os.environ,{'LLVM_PREBUILTS_BASE':'','LLVM_PREBUILTS_VERSION':''}), contextlib.redirect_stdout(io.StringIO()):
            inspect.preflight(source,evidence)
            inspect.capture('baseline',source,evidence,deliver)
            report=json.loads((evidence/'baseline-init.json').read_text())
            assert report['compiled_clang_producer']==PRODUCER
            assert report['unstripped_evidence']['text_section_matches'] is True
            assert (evidence/'baseline-disassembly.txt').is_file()
            assert report['flash_qualified'] is False
            assert report['selinux_compile_command']['status']=='UNAVAILABLE_DIAGNOSTIC'
            assert not (root/'LEGACY-EXECUTED').exists()
            assert any(row['path'].endswith('clang-3289846/bin/clang') and row['executed'] is False for row in report['clang_inventory'])
            cases.extend(['complete_capture_through_libraries_symbols_disassembly','unrelated_legacy_127_never_executed','optional_ninja_diagnostic_does_not_block'])
            selected.write_text('#!/bin/sh\nexit 127\n')
            try: inspect.preflight(source,evidence)
            except ValueError as error: assert 'exit 127' in str(error)
            else: raise AssertionError('selected compiler failure accepted')
            cases.append('selected_compiler_127_fails_preflight')
            selected.write_text('#!/bin/sh\nprintf "%s\\n" "'+PRODUCER+'"\n')
            with patch.dict(os.environ,{'LLVM_PREBUILTS_VERSION':'clang-unknown'}):
                try: inspect.preflight(source,evidence)
                except ValueError: pass
                else: raise AssertionError('compiler override accepted')
            cases.append('compiler_override_rejected')
            config=source/'build/soong/cc/config/global.go'; before=config.read_bytes(); config.write_bytes(before+b'\n')
            try: inspect.preflight(source,evidence)
            except ValueError: pass
            else: raise AssertionError('modified Soong config accepted')
            cases.append('modified_pinned_soong_config_rejected'); config.write_bytes(before)
            # Use all 396 real manifest entries, including repo's implicit-name paths.
            manifest=controls/'resolved-manifest.xml'; fixture_manifest=manifest.read_bytes()
            manifest.write_bytes((HERE/'resolved-manifest.xml').read_bytes())
            actual_projects={(p.attrib.get('path') or p.attrib['name']):p.attrib['revision']
                for p in inspect.ET.parse(manifest).getroot().findall('project')}
            def actual_manifest_git(args, **kwargs):
                if args[-1]=='HEAD':
                    relative=Path(args[2]).relative_to(source).as_posix()
                    return actual_projects[relative]+'\n'
                assert args[-1]=='HEAD:cc/config/global.go'
                data=config.read_bytes()
                return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()+'\n'
            with patch.object(inspect.subprocess,'check_output',side_effect=actual_manifest_git):
                assert inspect.selected_toolchain(source)['path'].endswith('clang-r547379/bin/clang')
            manifest.write_bytes(fixture_manifest)
            cases.append('all_396_actual_manifest_entries_including_implicit_paths')
            # The producer check must stop capture and retain only diagnostics.
            symbols=source/'out/target/product/sm8850/symbols/recovery/root/system/bin/init'
            symbols.write_bytes(symbols.read_bytes().replace(PRODUCER.encode(), b'X'*len(PRODUCER)))
            try: inspect.capture('baseline',source,evidence,deliver)
            except ValueError as error: assert 'producer differs' in str(error)
            else: raise AssertionError('different compiled producer accepted')
            assert not (evidence/'baseline-init.json').exists()
            assert (evidence/'baseline-capture-failure.json').is_file()
            cases.append('compiled_producer_mismatch_retains_unqualified_diagnostics')
    print(json.dumps({'status':'PASS','count':len(cases),'cases':cases,'real_android_compiler_executed':False,'elf_tools_mocked':True}))

if __name__=='__main__': main()
