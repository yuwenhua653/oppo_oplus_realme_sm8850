#!/usr/bin/env python3
"""Keep compiled init binaries separate from any flash-image qualification."""
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED_NEEDED = sorted(['libbase.so', 'libcutils.so', 'libext4_utils.so', 'libfs_mgr.so',
    'libgsi.so', 'liblog.so', 'liblogwrap.so', 'liblp.so', 'libprocessgroup.so',
    'libprocessgroup_setup.so', 'libselinux.so', 'libunwindstack.so', 'libvendorsupport.so',
    'libc++.so', 'libc.so', 'libm.so', 'libdl.so'])

def identity(p):
    with p.open('rb') as f:
        return {'bytes': p.stat().st_size, 'sha256': hashlib.file_digest(f, 'sha256').hexdigest()}

def elf_info(p):
    data = p.read_bytes()
    if len(data) < 64 or data[:6] != b'\x7fELF\x02\x01':
        raise ValueError('ELF64 little-endian required')
    if struct.unpack_from('<HH', data, 16) != (3, 183):
        raise ValueError('AArch64 PIE required')
    off = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    if size != 56 or off + size * count > len(data):
        raise ValueError('bad ELF program headers')
    interp = []
    stack_count = 0
    executable_loads = 0
    for n in range(count):
        entry = struct.unpack_from('<IIQQQQQQ', data, off + n * size)
        typ, flags, pos, _, _, length, mem_length, _ = entry
        if pos + length > len(data):
            raise ValueError('ELF segment exceeds file')
        if typ == 1 and flags & 3 == 3:
            raise ValueError('writable executable segment')
        if typ == 1 and length > mem_length:
            raise ValueError('load file size exceeds memory size')
        if typ == 1 and flags & 1 and length:
            executable_loads += 1
        if typ == 3:
            interp.append(data[pos:pos+length].rstrip(b'\0').decode())
        if typ == 0x6474e551:
            stack_count += 1
            if flags & 1:
                raise ValueError('executable stack')
    if interp != ['/system/bin/linker64']:
        raise ValueError('unexpected interpreter')
    if stack_count != 1:
        raise ValueError('exactly one nonexecutable GNU stack header required')
    if not executable_loads:
        raise ValueError('nonempty executable load segment required')
    dynamic = subprocess.check_output(['readelf', '-dW', str(p)], text=True)
    needed = sorted(re.findall(r'\(NEEDED\).*?\[([^\]]+)\]', dynamic))
    if needed != EXPECTED_NEEDED or '(RPATH)' in dynamic or '(RUNPATH)' in dynamic:
        raise ValueError('shared dependency list or search path differs from reference')
    return {'aarch64_pie': True, 'interpreter': interp[0], 'needed': needed,
            'non_writable_executable_segments': True, 'nonexecutable_stack': True}

def section(p, wanted):
    data = p.read_bytes()
    off = struct.unpack_from('<Q', data, 40)[0]
    size, count, names_index = struct.unpack_from('<HHH', data, 58)
    if size != 64 or not 0 < names_index < count or off + size * count > len(data):
        raise ValueError('invalid section table')
    rows = [struct.unpack_from('<IIQQQQIIQQ', data, off+i*size) for i in range(count)]
    names_row = rows[names_index]
    names = data[names_row[4]:names_row[4]+names_row[5]]
    for row in rows:
        name = names[row[0]:].split(b'\0', 1)[0].decode()
        if name == wanted:
            return data[row[4]:row[4]+row[5]]
    raise ValueError('missing '+wanted)

def capture(stage, source, evidence, deliver):
    lock = json.loads((HERE/'source-lock.json').read_text())
    product = source/'out/target/product/sm8850'
    binary = product/'recovery/root/system/bin/init'
    if not binary.is_file() or binary.is_symlink():
        raise ValueError('installed Recovery init missing or symlink')
    dst = deliver/stage
    dst.mkdir(parents=True, exist_ok=True)
    copy = dst/'init'
    shutil.copyfile(binary, copy)
    info = identity(copy)
    info['elf'] = elf_info(copy)
    info['source_selinux_sha256'] = identity(source/'system/core/init/selinux.cpp')['sha256']
    expected_source = lock['baseline_selinux_sha256' if stage == 'baseline' else 'candidate_selinux_sha256']
    if info['source_selinux_sha256'] != expected_source:
        raise ValueError('source does not match requested build stage')
    with (evidence/(stage+'-readelf.txt')).open('w') as f:
        subprocess.run(['readelf', '-hW', '-lW', '-dW', '-nW', '-Ws', str(copy)], stdout=f, check=True)
    libs = []
    for name in info['elf']['needed']:
        p = product/'recovery/root/system/lib64'/name
        if not p.is_file():
            raise ValueError('installed dependency missing: '+name)
        libs.append({'name':name, **identity(p)})
    info['installed_shared_libraries'] = libs
    clangs = sorted(source.glob('prebuilts/clang/host/linux-x86/clang-*/bin/clang'))
    info['available_clang_versions'] = []
    for p in clangs:
        version = subprocess.run([str(p), '--version'], capture_output=True, text=True, check=True)
        info['available_clang_versions'].append({'path':p.relative_to(source).as_posix(), 'version':version.stdout.strip()})
    candidates = [product/'symbols/recovery/root/system/bin/init']
    candidates += sorted(source.glob('out/soong/.intermediates/system/core/init/init_second_stage.recovery/*/unstripped/init'))
    seen = set()
    info['unstripped_evidence'] = 'unavailable; exact stripped init still retained'
    for p in candidates:
        if not p.is_file() or str(p.resolve()) in seen:
            continue
        seen.add(str(p.resolve()))
        if section(p, '.text') != section(copy, '.text'):
            continue
        elf_info(p)
        unstripped = dst/'init.unstripped'
        shutil.copyfile(p, unstripped)
        info['unstripped_evidence'] = {**identity(unstripped), 'text_section_matches':True,
                                      'source':p.relative_to(source).as_posix()}
        with (evidence/(stage+'-disassembly.txt')).open('w') as f:
            subprocess.run(['aarch64-linux-gnu-objdump','-dC',str(unstripped)], stdout=f, check=True)
        break
    if stage == 'baseline':
        info['matches_known_REC_init'] = (info['bytes'] == lock['baseline_init_bytes'] and info['sha256'] == lock['baseline_init_sha256'])
    info['flash_qualified'] = False
    (evidence/(stage+'-init.json')).write_text(json.dumps(info,indent=2)+'\n')
    print(json.dumps({'stage':stage, 'bytes':info['bytes'], 'sha256':info['sha256'],
                     'baseline_match':info.get('matches_known_REC_init'), 'flash_qualified':False}))

def finalize(evidence, deliver):
    baseline = json.loads((evidence/'baseline-init.json').read_text())
    patched = json.loads((evidence/'patched-init.json').read_text())
    if baseline['sha256'] == patched['sha256']:
        raise ValueError('selector source change did not change compiled init')
    if baseline['elf'] != patched['elf'] or baseline['installed_shared_libraries'] != patched['installed_shared_libraries']:
        raise ValueError('ELF ABI/dependency bytes changed between baseline and selector build')
    result = {'status':'COMPILED_INIT_CANDIDATE_REQUIRES_LOCAL_REVIEW', 'baseline':baseline, 'patched':patched,
              'known_baseline_matched':baseline['matches_known_REC_init'], 'source_projects_pinned':396,
              'kernel_built':False, 'recoveryimage_built':False, 'private_runtime_included':False,
              'flash_qualified':False, 'device_tested':False}
    (evidence/'BUILD-RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
    shutil.copyfile(evidence/'BUILD-RESULT.json', deliver/'BUILD-RESULT.json')
    shutil.copyfile(HERE/'selector/recovery-only-permissive.patch', deliver/'recovery-only-permissive.patch')
    shutil.copyfile(HERE/'source-lock.json', deliver/'source-lock.json')
    (deliver/'README.txt').write_text('Compiled Recovery init only. Not a flash image.\n'
        'Known baseline identity, exact source selection and ELF dependencies must be reviewed.\n'
        'Local Recovery repacking, PID1 contract review and actual device mode checks remain.\n'
        'Android system init and all private runtime modules are outside this workflow.\n')
    manifest = [{'path':p.relative_to(deliver).as_posix(),**identity(p)} for p in sorted(deliver.rglob('*')) if p.is_file()]
    (deliver/'FILES.json').write_text(json.dumps(manifest,indent=2)+'\n')

def main():
    action = sys.argv[1]
    temp = Path(os.environ['RUNNER_TEMP'])
    evidence, deliver, source = temp/'r99-evidence', temp/'r99-deliver', temp/'r97-aosp'
    if action in ('baseline','patched'):
        capture(action, source, evidence, deliver)
    elif action == 'finalize':
        finalize(evidence, deliver)
    elif action == 'qualify':
        result = json.loads((evidence/'BUILD-RESULT.json').read_text())
        if result['known_baseline_matched'] is not True:
            raise SystemExit('BASELINE MISMATCH: binaries were retained for inspection; no image qualification granted')
        print('PASS known baseline identity. Init candidate still needs local assembly and phone verification.')
    else:
        raise ValueError('unknown action')

if __name__ == '__main__':
    main()
