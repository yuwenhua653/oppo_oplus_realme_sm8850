#!/usr/bin/env python3
"""Build committed Redmi K90PM sources without applying patches or rewriting version strings."""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import dt_sandbox

SOURCE_PROFILE = 'myron-r123-device-validated-dt-source'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def validate_source_lock(lock):
    """Reject locks for other source generations before syncing or building."""
    actual = lock.get('profile') if isinstance(lock, dict) else None
    require(actual == SOURCE_PROFILE,
            'Wrong source manifest: expected profile ' + repr(SOURCE_PROFILE) +
            ', got ' + repr(actual))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()

def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def git(path, *args):
    return subprocess.check_output(['git', '-C', str(path), *args], text=True).strip()

def stamped_options(options):
    require(not any('stamp' in v or 'workspace_status_command' in v for v in options),
            'Unexpected inherited stamp override')
    return [*options, '--config=stamp']

def start_clock(now=None):
    # One current epoch is shared by all actions of this build, never HEAD's date.
    epoch = int(time.time() if now is None else now)
    stamp = datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc)
    os.environ['SOURCE_DATE_EPOCH'] = str(epoch)
    # Kleaf _setup_env.sh regenerates this using GNU date (space-padded day).
    os.environ['KBUILD_BUILD_TIMESTAMP'] = stamp.strftime('%a %b %e %H:%M:%S UTC %Y')
    for key in ('FAKETIME', 'FAKESTAT', 'LD_PRELOAD', 'LOCALVERSION', 'BUILD_NUMBER'):
        require(not os.environ.get(key), 'Unexpected time/version override: ' + key)
    return {'epoch': epoch, 'started_utc': stamp.isoformat(),
            'kbuild_timestamp': os.environ['KBUILD_BUILD_TIMESTAMP']}

def validate_release(release, head):
    require('dirty' not in release.lower() and 'maybe' not in release.lower() and 'mybe' not in release.lower(),
            'Unstamped placeholder in kernel.release')
    require(re.search(r'-g' + re.escape(head[:12]) + r'(?:-|$)', release),
            'kernel.release does not contain actual common Git HEAD')
    require(release.startswith('6.12.81-android16-6-') and release.endswith('-4k'),
            'Unexpected kernel/KMI/page-size version')

def verify_banner(image, release, clock):
    banners = re.findall(rb'Linux version [^\x00\r\n]{1,1024}', image.read_bytes())
    expected = ('Linux version ' + release + ' ').encode()
    matching = [b.decode('utf-8', 'replace') for b in banners if b.startswith(expected)]
    require(len(set(matching)) == 1, 'Expected one matching built Image banner')
    banner = matching[0]
    # Compare the actual UTC second, not %d (01) versus GNU date's %e ( 1).
    match = re.search(r'((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+'
                      r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+'
                      r'\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+UTC\s+\d{4})$', banner)
    require(match is not None, 'Missing UTC timestamp in Image banner: ' + banner)
    observed = datetime.datetime.strptime(' '.join(match[1].split()), '%a %b %d %H:%M:%S UTC %Y')
    observed = observed.replace(tzinfo=datetime.timezone.utc)
    require(observed.strftime('%a') == match[1].split()[0], 'Incorrect weekday in Image banner: ' + banner)
    require(int(observed.timestamp()) == clock['epoch'],
            'Image build date differs from actual build epoch: expected ' + clock['started_utc'] +
            ', observed ' + observed.isoformat() + '; banner=' + banner)
    return banner

def collect(root, output, paths, entry, clock, common_head):
    require(not output.exists(), 'Fresh full-build output required')
    output.mkdir(parents=True)
    write(output/'validation-status.json', {'verified': False, 'flashable': False,
          'note': 'Compilation outputs; validation is incomplete until this record says verified=true.'})
    selected=[]
    allowed={'Image','Image.gz','Image.lz4','System.map','Module.symvers','kernel.release',
             'modules.builtin','modules.builtin.modinfo','kernel_aarch64_dot_config','.config'}
    for name in sorted(set(paths)):
        rel=Path(name)
        require(not rel.is_absolute() and '..' not in rel.parts, 'Unsafe Bazel output')
        src=root/rel
        if not src.is_file() or not (src.name in allowed or src.suffix in ('.ko','.dtb','.dtbo','.symvers')):
            continue
        dst=output/'objects'/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
        selected.append({'source':name,'file':str(dst.relative_to(output)),'bytes':dst.stat().st_size,'sha256':sha(dst)})
    release_rows=[r for r in selected if Path(r['file']).name=='kernel.release']
    releases={(output/r['file']).read_text().strip() for r in release_rows}
    require(len(releases)==1, 'Missing or conflicting same-build kernel.release')
    release=releases.pop();validate_release(release,common_head)
    images=[output/r['file'] for r in selected if Path(r['file']).name=='Image']
    require(len({sha(p) for p in images})==1,'Missing or conflicting kernel Images')
    banner=verify_banner(images[0],release,clock)
    parser=load('r114_elf',entry/'elf_parser.py').parse_elf
    modules=[]
    for row in selected:
        if not row['file'].endswith('.ko'):continue
        elf=parser((output/row['file']).read_bytes())
        vermagic=elf['info']['vermagic']
        require(len(vermagic)==1 and vermagic[0].split()[0]==release,'Module vermagic mismatch: '+row['file'])
        modules.append({'name':elf['name'],'file':row['file'],'sha256':row['sha256'],'vermagic':vermagic[0]})
    require(len(modules)>=295,'Full module output unexpectedly small')
    required=set(json.loads((entry/'runtime-module-names.json').read_text())['required_module_names'])
    missing=sorted(required-{m['name'] for m in modules})
    require(not missing, 'Missing runtime modules: '+repr(missing))
    coverage={'required_names':len(required),'missing':missing,'abi_qualified':False}
    names={Path(r['file']).name for r in selected}
    require({'myron-sm8850-overlay.dtbo','myron-audio-mtp.dtbo','myron-sm8850-camera-sensor.dtbo',
             'myron-sde-display-mtp-overlay.dtbo','Module.symvers'}<=names,'Missing full-build DT/kernel outputs')
    result={'kernel_release':release,'linux_banner':banner,'module_file_count':len(modules),
            'unique_module_names':len({m['name'] for m in modules}),'modules':modules,'files':selected,'runtime_name_coverage':coverage,
            'flashable':False,'installed_module_abi_compatible':'NOT_CHECKED',
            'note':'All outputs from this stamped build. Includes reference/alternative modules; not an autoload list.'}
    write(output/'artifact-manifest.json',result)
    write(output/'assembly-status.json',{'ready_to_flash':False,
        'baseline_sources_included':False,'recovery_image_in_this_artifact':False,
        'selinux_and_recovery_assembly':'Separate partition assembly is required; this repository builds kernel and modules'})
    (output/'NOT-A-FLASH-PACKAGE.txt').write_text('红米 K90PM / myron 完整源码编译产物。新版本模块需与新内核成套装配；本目录不是刷机包，也不是自动加载清单。\n')
    write(output/'validation-status.json', {'verified': True, 'flashable': False,
          'kernel_release': release, 'linux_banner': banner, 'runtime_name_coverage': coverage})
    return {k:result[k] for k in ('kernel_release','linux_banner','module_file_count','unique_module_names')}


def check_sources(root, lock):
    result = []
    for p in lock['projects']:
        path = root / p['path']
        head = git(path, 'rev-parse', 'HEAD')
        require(head == p['commit'], 'Source revision differs: ' + p['path'])
        require(not git(path, 'status', '--porcelain', '--untracked-files=normal'),
                'Uncommitted source changes: ' + p['path'])
        require(not (path / '.scmversion').exists(), 'SCM version override: ' + p['path'])
        result.append({'path': p['path'], 'commit': head})
    return result


def logged(command, root, path):
    with path.open('w') as log:
        log.write('$ ' + ' '.join(command) + '\n')
        proc = subprocess.Popen(command, cwd=root, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            log.write(line)
            log.flush()
            if not line.startswith('DEBUG:'):
                print(line, end='', flush=True)
        require(proc.wait() == 0, 'Build command failed; see ' + str(path))


def query_outputs(command, root, reports, name):
    result = subprocess.run(command, cwd=root, capture_output=True, text=True)
    (reports / (name + '.txt')).write_text(result.stdout)
    (reports / (name + '.log')).write_text(result.stderr)
    require(result.returncode == 0, 'Output enumeration failed: ' + name)
    return result.stdout.splitlines()


def check_kernel_before_modules(root, paths, head, clock, reports):
    """Check the real Image before spending time compiling external modules."""
    record = {'verified': False, 'flashable': False, 'expected_epoch': clock['epoch'],
              'expected_utc': clock['started_utc'], 'common_commit': head}
    output = root / 'integration-artifacts/kernel-diagnostic'
    output.mkdir(parents=True, exist_ok=True)
    write(output / 'validation-status.json', record)
    try:
        files = {'Image': [], 'kernel.release': []}
        for name in paths:
            rel = Path(name)
            require(not rel.is_absolute() and '..' not in rel.parts, 'Unsafe Bazel output')
            if rel.name in files and (root / rel).is_file():
                files[rel.name].append(root / rel)
        for name, sources in files.items():
            require(len({sha(p) for p in sources}) == 1, 'Missing/conflicting kernel output: ' + name)
            shutil.copy2(sources[0], output / name)
        release = (output / 'kernel.release').read_text().strip()
        record['kernel_release'] = release
        record['linux_banners'] = [b.decode('utf-8', 'replace') for b in
            re.findall(rb'Linux version [^\x00\r\n]{1,1024}', (output / 'Image').read_bytes())]
        validate_release(release, head)
        record['linux_banner'] = verify_banner(output / 'Image', release, clock)
        record['verified'] = True
    except Exception as error:
        record['error'] = str(error)
        raise
    finally:
        write(reports / 'kernel-preflight.json', record)
        write(output / 'validation-status.json', record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path('kernel_workspace'))
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--ram-mb', type=int, default=10000)
    parser.add_argument('--sync-jobs', type=int, default=4)
    parser.add_argument('--no-sync', action='store_true')
    a = parser.parse_args()
    require(a.jobs >= 1 and a.ram_mb >= 2048 and 1 <= a.sync_jobs <= 16, 'Invalid resource limits')
    entry = Path(__file__).resolve().parent
    root = a.workspace.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    reports = root / 'integration-reports'
    reports.mkdir(exist_ok=True)
    state = {'success': False, 'compiled': False, 'flashable': False,
             'device': 'Redmi K90PM / myron', 'entry_commit': git(entry, 'rev-parse', 'HEAD')}
    started = time.monotonic()
    try:
        lock = json.loads((entry / 'sources.lock.json').read_text())
        validate_source_lock(lock)
        if not a.no_sync:
            logged([sys.executable, '-B', str(entry / 'sync_sources.py'), '--workspace', str(root),
                    '--jobs', str(a.sync_jobs)], entry, reports / 'source-sync.log')
        import sync_sources
        sync_sources.link_sources(root, lock)
        before = check_sources(root, lock)
        metadata = root / 'myron_artifact_metadata/BUILD.bazel'
        data = (entry / 'metadata.BUILD.bazel').read_bytes()
        require(not metadata.is_symlink(), 'Redirected metadata file')
        require(not metadata.exists() or metadata.read_bytes() == data, 'Changed metadata target')
        metadata.parent.mkdir(parents=True, exist_ok=True)
        metadata.write_bytes(data)
        targets = json.loads((entry / 'targets.json').read_text())
        require('//vendor/qcom/sm8850:myron_platform_lab' in targets, 'Full build graph required')
        head = next(p['commit'] for p in lock['projects'] if p['path'] == 'common')
        bazel = [str(root / 'tools/bazel'), '--batch', '--host_jvm_args=-Xmx2g',
                 '--output_base=' + str(root / 'out/bazel-integration')]
        options = ['--cpu=aarch64', '--//build/kernel/kleaf:allow_ddk_unsafe_headers',
                   '--//build/kernel/kleaf:user_ddk_unsafe_headers=//vendor/qcom/sm8850:unsafe_headers_qcom_group',
                   '--jobs=' + str(a.jobs), '--local_ram_resources=' + str(a.ram_mb),
                   '--color=no', '--curses=no', '--show_progress', '--show_progress_rate_limit=30',
                   '--progress_report_interval=30', '--nokeep_going', '--config=stamp']
        os.environ['KLEAF_EXTRA_GIT_PROJECTS'] = ':'.join(p['path'] for p in lock['projects'])
        os.environ['CCACHE_NODEBUG'] = 'true'
        os.environ.pop('CCACHE_DEBUG', None)
        clock = start_clock()
        state.update(clock, phase='compile', sources=before)
        write(reports / 'build-status.json', state)
        compile_start = time.monotonic()
        commands = {
            'kconfig': bazel + ['build'] + options + ['//vendor/qcom/sm8850:kconfig.msm.generated'],
            'config': bazel + ['build'] + options + ['//vendor/qcom/sm8850:canoe_perf_config'],
            'kernel': bazel + ['build'] + options + ['//common:kernel_aarch64', '//myron_artifact_metadata:kernel_release'],
            'kernel_outputs': bazel + ['cquery'] + options + ['--output=files',
                'deps(set(//common:kernel_aarch64 //myron_artifact_metadata:kernel_release))'],
            'build': bazel + ['build'] + options + targets,
            'outputs': bazel + ['cquery'] + options + ['--output=files', 'deps(set(' + ' '.join(targets) + '))'],
        }
        write(reports / 'commands.json', commands)
        for name in ('kconfig', 'config'):
            logged(commands[name], root, reports / (name + '.log'))
        dt_sandbox.preflight(root, reports, bazel, options)
        state['phase'] = 'kernel_timestamp_preflight'
        write(reports / 'build-status.json', state)
        logged(commands['kernel'], root, reports / 'kernel-build.log')
        kernel_paths = query_outputs(commands['kernel_outputs'], root, reports, 'kernel-outputs')
        kernel = check_kernel_before_modules(root, kernel_paths, head, clock, reports)
        state.update(kernel_compiled=True, kernel_release=kernel['kernel_release'],
                     linux_banner=kernel['linux_banner'], phase='compile_all_modules')
        write(reports / 'build-status.json', state)
        logged(commands['build'], root, reports / 'full-build.log')
        state.update(compiled=True, phase='validate_full_outputs')
        state['compile_elapsed_seconds'] = round(time.monotonic() - compile_start, 3)
        write(reports / 'build-status.json', state)
        paths = query_outputs(commands['outputs'], root, reports, 'outputs')
        require(check_sources(root, lock) == before, 'Sources changed during compilation')
        state.update(collect(root, root / 'integration-artifacts/full', paths,
                             entry, clock, head))
        state.update(success=True, compiled=True, phase='verified_clean_source_build')
    except Exception as error:
        state.update(phase='failed', error=str(error))
        print('ERROR:', error, file=sys.stderr)
    finally:
        state['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        state['total_elapsed_seconds'] = round(time.monotonic() - started, 3)
        write(reports / 'build-status.json', state)
        print(json.dumps(state, indent=2))
    return 0 if state['success'] else 1


if __name__ == '__main__':
    sys.exit(main())

