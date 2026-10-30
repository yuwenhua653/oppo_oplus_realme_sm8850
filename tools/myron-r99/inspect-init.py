#!/usr/bin/env python3
"""Keep compiled init binaries separate from any flash-image qualification."""
import hashlib
import json
import os
import re
import shlex
import shutil
import struct
import subprocess
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
EXPECTED_NEEDED = sorted(['libbase.so', 'libcutils.so', 'libext4_utils.so', 'libfs_mgr.so',
    'libgsi.so', 'liblog.so', 'liblogwrap.so', 'liblp.so', 'libprocessgroup.so',
    'libprocessgroup_setup.so', 'libselinux.so', 'libunwindstack.so', 'libvendorsupport.so',
    'libc++.so', 'libc.so', 'libm.so', 'libdl.so'])

def identity(p):
    with p.open('rb') as f:
        return {'bytes': p.stat().st_size, 'sha256': hashlib.file_digest(f, 'sha256').hexdigest()}

def selected_toolchain(source):
    """Verify the pinned Soong selection; never execute unrelated legacy Clang."""
    projects = {(p.attrib.get('path') or p.attrib['name']): p.attrib['revision'] for p in
                ET.parse(HERE/'resolved-manifest.xml').getroot().findall('project')}
    heads = {}
    for path in ('build/soong', 'prebuilts/clang/host/linux-x86'):
        head = subprocess.check_output(['git', '-C', str(source/path),
                                        'rev-parse', 'HEAD'], text=True).strip()
        if head != projects[path]:
            raise ValueError('toolchain project commit mismatch: '+path)
        heads[path] = head
    config = source/'build/soong/cc/config/global.go'
    data = config.read_bytes()
    blob = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    expected = subprocess.check_output(['git', '-C', str(source/'build/soong'),
        'rev-parse', 'HEAD:cc/config/global.go'], text=True).strip()
    if config.is_symlink() or blob != expected:
        raise ValueError('Soong compiler selection source differs from pinned Git blob')
    selections = {}
    for name, env in [('ClangDefaultBase', 'LLVM_PREBUILTS_BASE'),
                      ('ClangDefaultVersion', 'LLVM_PREBUILTS_VERSION')]:
        values = re.findall(r'^\s*'+name+r'\s*=\s*"([^"\n]+)"\s*$', data.decode(), re.M)
        if len(values) != 1:
            raise ValueError('ambiguous Soong compiler selection: '+name)
        if os.environ.get(env, values[0]) not in ('', values[0]):
            raise ValueError('unreviewed compiler override: '+env)
        selections[name] = values[0]
    relative = Path(selections['ClangDefaultBase'])/'linux-x86'/selections['ClangDefaultVersion']/'bin/clang'
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('compiler path escapes pinned source')
    compiler = source/relative
    if not compiler.is_file() or not compiler.resolve().is_relative_to(source.resolve()):
        raise ValueError('selected compiler missing or escapes source')
    try:
        version = subprocess.run([str(compiler), '--version'], capture_output=True,
                                 text=True, check=True, timeout=15)
    except subprocess.CalledProcessError as error:
        detail = ((error.stderr or '') + '\n' + (error.stdout or '')).strip()[:4096]
        raise ValueError('selected compiler --version failed with exit '+str(error.returncode)+': '+detail) from error
    if not version.stdout.strip() or 'clang version ' not in version.stdout.splitlines()[0]:
        raise ValueError('selected compiler returned no Clang producer version')
    return {'project_heads': heads, 'soong_config': {**identity(config), 'git_blob': blob},
            'path': relative.as_posix(), **identity(compiler), 'version': version.stdout.strip(),
            'selection': 'pinned Soong defaults; differing environment overrides rejected'}

def preflight(source, evidence):
    """Fail before compilation if selected compiler or inspection tools cannot run."""
    report = {'status': 'PASS', 'selected_toolchain': selected_toolchain(source), 'inspection_tools': {}}
    for name in ('readelf', 'aarch64-linux-gnu-objdump'):
        tool = shutil.which(name)
        if tool is None:
            raise ValueError('required inspection tool missing: '+name)
        version = subprocess.run([tool, '--version'], capture_output=True, text=True,
                                 check=True, timeout=15)
        report['inspection_tools'][name] = {'path': tool, 'version': version.stdout.splitlines()[0]}
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence/'toolchain-preflight.json').write_text(json.dumps(report, indent=2)+'\n')
    return report

def _compile_command(source, selected, evidence, stage):
    """Try Ninja's expanded command for the Recovery SELinux object."""
    objects = sorted(p for p in (source/'out/soong/.intermediates/system/core/init/libinit').rglob('selinux.o')
                     if any(x.startswith('android_recovery_') for x in p.parts) and p.is_file())
    if len(objects) != 1:
        raise ValueError('expected one compiled Recovery selinux.o, found '+str(len(objects)))
    target = objects[0].relative_to(source).as_posix()
    ninja = source/'prebuilts/build-tools/linux-x86/bin/ninja'
    graph = 'out/soong/build.twrp_sm8850.ninja'
    result = subprocess.run([str(ninja), '-f', graph, '-t', 'commands', target],
                            cwd=source, capture_output=True, text=True, check=True, timeout=30)
    commands = []
    for line in result.stdout.splitlines():
        tokens = shlex.split(line)
        if '-c' in tokens and 'system/core/init/selinux.cpp' in tokens:
            if '-o' in tokens and tokens[tokens.index('-o')+1:tokens.index('-o')+2] == [target]:
                commands.append((line, tokens))
    if len(commands) != 1:
        raise ValueError('missing or ambiguous actual Recovery SELinux compile command')
    command, tokens = commands[0]
    compiler = str(Path(selected['path']).with_name('clang++'))
    if compiler not in tokens or '-DRECOVERY' not in tokens:
        raise ValueError('actual Recovery compiler/define differs from selected toolchain')
    path = evidence/(stage+'-selinux-compile-command.txt')
    path.write_text(command+'\n')
    return {'object': target, 'compiler': compiler, 'recovery_define': True,
            'expanded_command_sha256': identity(path)['sha256']}

def compile_command(source, selected, evidence, stage):
    # Graph/object layout is diagnostic only. Toolchain identity is instead
    # required by the pinned config, selected executable, and matching-text ELF
    # producer below; do not fail a completed compile on an optional query.
    try:
        return {'status': 'CAPTURED', **_compile_command(source, selected, evidence, stage)}
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return {'status': 'UNAVAILABLE_DIAGNOSTIC', 'error_type': type(error).__name__,
                'error': str(error), 'qualification_granted': False}

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
    """Retain raw diagnostics before any qualification check can fail."""
    evidence.mkdir(parents=True, exist_ok=True)
    destination = deliver/stage
    destination.mkdir(parents=True, exist_ok=True)
    (evidence/(stage+'-init.json')).unlink(missing_ok=True)
    product = source/'out/target/product/sm8850'
    lock = json.loads((HERE/'source-lock.json').read_text())
    diagnostic = {'stage':stage, 'status':'UNQUALIFIED_DIAGNOSTIC_CAPTURE',
                  'flash_qualified':False, 'files':{}, 'source_files':{}}
    if stage == 'baseline':
        diagnostic['expected_known_baseline'] = {'bytes':lock['baseline_init_bytes'],'sha256':lock['baseline_init_sha256']}
    for name, original in [('init',product/'recovery/root/system/bin/init'),
                           ('init.unstripped.raw',product/'symbols/recovery/root/system/bin/init')]:
        if original.is_file() and not original.is_symlink():
            target = destination/name
            shutil.copyfile(original,target)
            diagnostic['files'][name] = identity(target)
            result = subprocess.run(['readelf','-hW','-lW','-dW','-nW','-Ws',str(target)],capture_output=True)
            (evidence/(stage+'-'+name+'-raw-readelf.txt')).write_bytes(result.stdout+result.stderr)
            diagnostic['files'][name]['readelf_exit_code'] = result.returncode
    for name in ('selinux.cpp','Android.bp'):
        original = source/'system/core/init'/name
        if original.is_file() and not original.is_symlink():
            (evidence/(stage+'-actual-'+name)).write_bytes(original.read_bytes())
            diagnostic['source_files'][name] = identity(original)
    (destination/'UNQUALIFIED-CAPTURE.json').write_text(json.dumps(diagnostic,indent=2)+'\n')
    (destination/'NOT-FLASHABLE.txt').write_text('Raw compiler diagnostics. Validation is incomplete until stage checks finish.\nNot a flash image; do not install or execute these files on a phone.\n')
    try:
        _capture_checked(stage,source,evidence,deliver)
    except Exception as error:
        diagnostic.update(status='CAPTURE_VALIDATION_FAILED',error_type=type(error).__name__,error=str(error))
        (evidence/(stage+'-capture-failure.json')).write_text(json.dumps(diagnostic,indent=2)+'\n')
        (destination/'UNQUALIFIED-CAPTURE.json').write_text(json.dumps(diagnostic,indent=2)+'\n')
        raise

def _capture_checked(stage, source, evidence, deliver):
    from source_checks import check_source
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
    check_source(source,stage,lock,evidence/(stage+'-postcompile-source.json'))
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
    info['selected_toolchain'] = selected_toolchain(source)
    before = json.loads((evidence/'toolchain-preflight.json').read_text())
    if before['selected_toolchain'] != info['selected_toolchain']:
        raise ValueError('selected toolchain changed since preflight')
    info['selinux_compile_command'] = compile_command(source, info['selected_toolchain'], evidence, stage)
    info['clang_inventory'] = [{'path': p.relative_to(source).as_posix(),
                                'executed': p.relative_to(source).as_posix() == info['selected_toolchain']['path']}
        for p in sorted(source.glob('prebuilts/clang/host/linux-x86/clang-*/bin/clang'))]
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
        producer = info['selected_toolchain']['version'].splitlines()[0]
        comments = section(p, '.comment').decode().split('\0')
        if producer not in comments:
            raise ValueError('compiled ELF producer differs from selected compiler')
        info['compiled_clang_producer'] = producer
        unstripped = dst/'init.unstripped'
        shutil.copyfile(p, unstripped)
        info['unstripped_evidence'] = {**identity(unstripped), 'text_section_matches':True,
                                      'source':p.relative_to(source).as_posix()}
        with (evidence/(stage+'-disassembly.txt')).open('w') as f:
            subprocess.run(['aarch64-linux-gnu-objdump','-dC',str(unstripped)], stdout=f, check=True)
        break
    if 'compiled_clang_producer' not in info:
        raise ValueError('matching-text symbols with selected compiler producer required')
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
    if action == 'preflight':
        print(json.dumps(preflight(source, evidence)))
    elif action in ('baseline','patched'):
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
