#!/usr/bin/env python3
"""Full K90PM/myron source build with real Git stamping and wall-clock time."""
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
import dt_source_bridge
import dt_sandbox

CORE_HEAD = '41a2024a9e2eb66ab0643a865d74943b4ee3cff8'
BASE_HEAD = '7b74ce235cabd1f966a679c9fc03ceda1e6160f5'
FULL_TARGET = '//vendor/qcom/sm8850:myron_platform_lab'

def require(ok, message):
    if not ok:
        raise ValueError(message)

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
    os.environ['KBUILD_BUILD_TIMESTAMP'] = stamp.strftime('%a %b %d %H:%M:%S UTC %Y')
    for key in ('FAKETIME', 'FAKESTAT', 'LD_PRELOAD', 'LOCALVERSION', 'BUILD_NUMBER'):
        require(not os.environ.get(key), 'Unexpected time/version override: ' + key)
    return {'epoch': epoch, 'started_utc': stamp.isoformat(),
            'kbuild_timestamp': os.environ['KBUILD_BUILD_TIMESTAMP']}

def validate_release(release, head):
    require('maybe' not in release.lower() and 'mybe' not in release.lower(),
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
    require(clock['kbuild_timestamp'] in banner, 'Image build date differs from actual build epoch')
    return banner

def source_snapshot(root, lock, reports):
    rows=[]
    for project in lock['projects']:
        path=root/project['path']
        require(git(path, 'rev-parse', 'HEAD') == project['commit'], 'Source HEAD changed: '+project['path'])
        # Capture tracked source changes and nonignored new files, not credentials or env.
        changed=subprocess.check_output(['git','-C',str(path),'ls-files','-m','-o','--exclude-standard','-z']).split(b'\0')
        paths=sorted({p.decode() for p in changed if p})
        files=[]
        for rel in paths:
            p=path/rel
            if p.is_symlink():files.append({'path':rel,'symlink':os.readlink(p)})
            elif p.is_file():files.append({'path':rel,'sha256':sha(p)})
            else:files.append({'path':rel,'deleted':True})
        patch=subprocess.check_output(['git','-C',str(path),'diff','--binary','HEAD'])
        patchfile=reports/'source-diffs'/(project['path'].replace('/','_')+'.patch')
        patchfile.parent.mkdir(parents=True,exist_ok=True);patchfile.write_bytes(patch)
        rows.append({'path':project['path'],'head':project['commit'],'files':files,'tracked_diff_sha256':hashlib.sha256(patch).hexdigest()})
    return rows

def collect(root, output, paths, repo, clock):
    require(not output.exists(), 'Fresh full-build output required')
    output.mkdir(parents=True)
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
    release=releases.pop();validate_release(release,CORE_HEAD)
    images=[output/r['file'] for r in selected if Path(r['file']).name=='Image']
    require(len({sha(p) for p in images})==1,'Missing or conflicting kernel Images')
    banner=verify_banner(images[0],release,clock)
    parser=load('r114_elf',repo/'r92-build-route/reference/r18_elf_parser.py').parse_elf
    modules=[]
    for row in selected:
        if not row['file'].endswith('.ko'):continue
        elf=parser((output/row['file']).read_bytes())
        vermagic=elf['info']['vermagic']
        require(len(vermagic)==1 and vermagic[0].split()[0]==release,'Module vermagic mismatch: '+row['file'])
        modules.append({'name':elf['name'],'file':row['file'],'sha256':row['sha256'],'vermagic':vermagic[0]})
    require(len(modules)>=295,'Full module output unexpectedly small')
    names={Path(r['file']).name for r in selected}
    require({'myron-sm8850-overlay.dtbo','myron-audio-mtp.dtbo','myron-sm8850-camera-sensor.dtbo',
             'myron-sde-display-mtp-overlay.dtbo','Module.symvers'}<=names,'Missing full-build DT/kernel outputs')
    result={'kernel_release':release,'linux_banner':banner,'module_file_count':len(modules),
            'unique_module_names':len({m['name'] for m in modules}),'modules':modules,'files':selected,
            'flashable':False,'installed_module_abi_compatible':'NOT_CHECKED',
            'note':'All outputs from this stamped build. Includes reference/alternative modules; not an autoload list.'}
    write(output/'artifact-manifest.json',result)
    write(output/'assembly-status.json',{'ready_to_flash':False,
        'baseline_sources_included':False,'recovery_image_in_this_artifact':False,
        'selinux_and_recovery_assembly':'Retained locally for subsequent integration; not uploaded with this kernel source build'})
    (output/'NOT-A-FLASH-PACKAGE.txt').write_text('红米 K90PM / myron 完整源码编译产物。新版本模块需与新内核成套装配；本目录不是刷机包，也不是自动加载清单。\n')
    return {k:result[k] for k in ('kernel_release','linux_banner','module_file_count','unique_module_names')}

def dt_inputs(output, names):
    manifest=json.loads((output/'artifact-manifest.json').read_text())
    require(manifest.get('flashable') is False,'DT inputs must be non-flashable')
    result=[]
    for name in names:
        rows=[r for r in manifest['files'] if Path(r['file']).name==name]
        require(bool(rows),'Missing DT merge input: '+name)
        paths=[]
        for row in rows:
            rel=Path(row['file']);path=(output/rel).resolve()
            require(not rel.is_absolute() and '..' not in rel.parts and path.is_relative_to(output.resolve()),'Unsafe DT input path')
            require(path.is_file() and sha(path)==row['sha256'],'DT input hash mismatch: '+name)
            paths.append(path)
        require(len({sha(p) for p in paths})==1,'Conflicting DT merge inputs: '+name)
        result.append(paths[0])
    return result

def validate_dt(root, repo, output, reports):
    dt_source_bridge.migrate(repo,verify=True)
    sys.path.insert(0,str(repo/'myron-adaptation-r12/dt'))
    validator=load('r114_dt_validator',repo/'myron-adaptation-r12/dt/validate_dt.py')
    report={'success':False,'merge_passed':False,'flashable':False,'hardware_tested':False,
            'scope':'Diagnostic composition; preserve OEM DTB/DTBO during partition assembly'}
    try:
        require(git(root/dt_source_bridge.DT,'rev-parse','HEAD')==validator.DT_REVISION,'Unexpected DT revision')
        tool_dir=root/'integration-cache/myron-r114-dt-tools'
        report['tool_provenance']=validator.build_tools(root,tool_dir)
        inputs=dt_inputs(output,validator.INPUTS)
        validator.merge_and_check(inputs,tool_dir,reports/'r114-dt-merge',report)
        report['success']=True
    except Exception as error:
        report['error']=str(error)
        raise
    finally:
        write(reports/'r114-dt-merge.json',report)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('workspace','package','baseline','r18','repo-root'):ap.add_argument('--'+n,type=Path,required=True)
    ap.add_argument('--jobs',type=int,default=2);ap.add_argument('--ram-mb',type=int,default=10000)
    a=ap.parse_args();root=a.workspace.resolve();repo=a.repo_root.resolve();reports=root/'integration-reports'
    reports.mkdir(parents=True,exist_ok=True)
    state={'device':'Redmi K90PM','round':'R114','success':False,'compiled':False,'flashable':False,
           'integration_base_commit':BASE_HEAD,'workflow_commit':os.environ.get('GITHUB_SHA'),
           'run_url':'https://github.com/'+os.environ.get('GITHUB_REPOSITORY','')+'/actions/runs/'+os.environ.get('GITHUB_RUN_ID','')}
    start=time.monotonic()
    try:
        require(1<=a.jobs<=4 and a.ram_mb>=2048,'Invalid resources')
        sys.path.insert(0,str(repo/'r94-build-route'))
        led=load('r114_r94',repo/'r94-build-route/build_led.py')
        patch=led.check_patch(repo/'r94-build-route')
        require(led.pin((repo/'r92-build-route/build_pd_provider.py').read_bytes())['sha256']==led.R92_ENGINE_SHA,'R92 engine changed')
        sys.path.insert(0,str(repo/'r92-build-route'))
        parent=load('r114_r92',repo/'r92-build-route/build_pd_provider.py')
        boundary=dt_source_bridge.boundary(parent.Boundary,repo);boundary.check(repo)
        state['phase']='prepare_existing_driver_fixes';write(reports/'r114-status.json',state)
        scope=led.prepare(boundary,a,reports,state)
        dt_sandbox.apply(root,reports)
        led.patch_source(root,repo/'r94-build-route',patch)
        runner=scope['runner']
        for path,arguments in [
            ('myron-boot-r18/source-fix/apply_soccp.py',['--soc',str(root/'vendor/qcom/sm8850')]),
            ('r55-source/dsp-auto-boot/apply_dsp_auto_boot.py',['--soc',str(root/'vendor/qcom/sm8850')]),
            ('r81-build-route/apply_wifi.py',['--workspace',str(root)]),
            ('r82-build-route/apply_cnss.py',['--workspace',str(root)])]:
            runner.logged([sys.executable,'-B',str(repo/path),*arguments],root,reports/('r114-'+Path(path).parent.name+'.log'))
        # R80 forced-NSS trial is deliberately absent; R81 retains normal NSS.
        lock=json.loads((a.package/'sources.lock.json').read_text())
        before=source_snapshot(root,lock,reports)
        write(reports/'r114-prebuild-source-state.json',before)
        require(git(root/'common','rev-parse','HEAD')==CORE_HEAD,'Wrong common source')
        require(not (root/'common/.scmversion').exists(),'Unexpected source SCM override')
        options=stamped_options(scope['options']);bazel=scope['bazel']
        targets=runner.build_targets(root,'full')
        targets=list(dict.fromkeys(targets+scope['contract']['core_targets']+
                      [r['target'] for r in scope['contract']['validation_only_modules']]+[led.MODULE['target']]))
        require(FULL_TARGET in targets and '//common:kernel_aarch64_modules' in targets,'Full build graph required')
        clock=start_clock();state.update(clock);state['phase']='full_stamped_compile';write(reports/'r114-status.json',state)
        # Use the upstream stamp implementation. Its SOURCE_DATE_EPOCH override
        # is current wall clock; SCMVERSION still comes from actual Git state.
        os.environ['KLEAF_EXTRA_GIT_PROJECTS']=':'.join(p['path'] for p in lock['projects'])
        commands={'kconfig':bazel+['build']+options+['//vendor/qcom/sm8850:kconfig.msm.generated'],
                  'config':bazel+['build']+options+['//vendor/qcom/sm8850:canoe_perf_config'],
                  'build':bazel+['build']+options+targets,
                  'outputs':bazel+['cquery']+options+['--output=files','deps(set('+' '.join(targets)+'))']}
        write(reports/'r114-commands.json',commands)
        for stage in ('kconfig','config'):
            runner.logged(commands[stage],root,reports/('r114-'+stage+'.log'))
        state['phase']='verify_dt_sandbox_inputs';write(reports/'r114-status.json',state)
        dt_sandbox.preflight(root,reports,bazel,options)
        state['phase']='full_stamped_compile';write(reports/'r114-status.json',state)
        runner.logged(commands['build'],root,reports/'r114-full-build.log')
        out=subprocess.run(commands['outputs'],cwd=root,capture_output=True,text=True)
        (reports/'r114-cquery.txt').write_text(out.stdout);(reports/'r114-cquery.log').write_text(out.stderr)
        require(out.returncode==0,'Full output enumeration failed')
        after=source_snapshot(root,lock,reports/'postbuild')
        require(before==after,'Tracked/nonignored source state changed during compilation')
        state.update(collect(root,root/'integration-artifacts/r114-full',out.stdout.splitlines(),repo,clock))
        state.update(compiled=True,phase='validate_compiled_dt_merge')
        write(reports/'r114-status.json',state)
        validate_dt(root,repo,root/'integration-artifacts/r114-full',reports)
        state.update(success=True,compiled=True,phase='full_compile_verified_pending_packaging')
    except Exception as e:
        state.update(phase='failed',error=str(e));print('R114 ERROR:',e,file=sys.stderr)
    finally:
        state['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        state['elapsed_seconds']=round(time.monotonic()-start,3)
        write(reports/'r114-status.json',state)
        print(json.dumps(state,indent=2))
    return 0 if state['success'] else 1

if __name__=='__main__':sys.exit(main())
