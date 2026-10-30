#!/usr/bin/env python3
"""Run the production stage shell against narrow compiler/tool fixtures."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE=Path(__file__).resolve().parent
BASELINE=b'HOST BASELINE FIXTURE\n'
INSPECTOR='''import hashlib,json,os,sys
from pathlib import Path
def identity(p): return {'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def selected_toolchain(source): return {'fixture':os.environ.get('R99_TEST_TOOLCHAIN','same')}
if __name__=='__main__':
    action=sys.argv[1]; temp=Path(os.environ['RUNNER_TEMP']); evidence=temp/'r99-evidence'
    with Path(os.environ['R99_TEST_EVENTS']).open('a') as out:out.write('inspect:'+action+'\\n')
    if os.environ.get('R99_TEST_FAIL')==action: raise SystemExit(51)
    if action=='preflight':
        (evidence/'toolchain-preflight.json').write_text(json.dumps({'status':'PASS','selected_toolchain':selected_toolchain(None)}))
    else:
        binary=temp/'r97-aosp/out/target/product/sm8850/recovery/root/system/bin/init'
        dest=temp/'r99-deliver'/action/'init';dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(binary.read_bytes())
        (evidence/(action+'-init.json')).write_text(json.dumps({**identity(binary),'matches_known_REC_init':action=='baseline'}))
'''
SOURCE_CHECK='''import os,sys
from pathlib import Path
with Path(os.environ['R99_TEST_EVENTS']).open('a') as out:out.write('source:'+sys.argv[2]+'\\n')
if os.environ.get('R99_TEST_FAIL')=='source:'+sys.argv[2]:raise SystemExit(52)
'''
SELECTOR='''import os
from pathlib import Path
with Path(os.environ['R99_TEST_EVENTS']).open('a') as out:out.write('selector\\n')
if os.environ.get('R99_TEST_FAIL')=='selector':raise SystemExit(53)
'''
ENVSETUP='''lunch() { export TARGET_PRODUCT=twrp_sm8850 TARGET_BUILD_VARIANT=eng; }
m() {
    printf 'm:%s\\n' "$R99_TEST_STAGE" >> "$R99_TEST_EVENTS"
    [ "$R99_TEST_FAIL" = compiler ] && return 54
    mkdir -p out/target/product/sm8850/recovery/root/system/bin
    if [ "$R99_TEST_STAGE" = baseline ]; then
        printf 'HOST BASELINE FIXTURE\\n' > out/target/product/sm8850/recovery/root/system/bin/init
    else
        printf 'HOST PATCHED FIXTURE\\n' > out/target/product/sm8850/recovery/root/system/bin/init
    fi
}
'''

def setup(root):
    workspace=root/'workspace';adapt=workspace/'tools/myron-r99';adapt.mkdir(parents=True)
    shutil.copyfile(HERE/'compile.sh',adapt/'compile.sh')
    (adapt/'inspect-init.py').write_text(INSPECTOR)
    (adapt/'source_checks.py').write_text(SOURCE_CHECK)
    (adapt/'apply-selector.py').write_text(SELECTOR)
    (adapt/'source-lock.json').write_text(json.dumps({'baseline_init_bytes':len(BASELINE),'baseline_init_sha256':hashlib.sha256(BASELINE).hexdigest()}))
    temp=root/'runner';(temp/'r99-evidence').mkdir(parents=True);(temp/'r99-deliver').mkdir()
    source=temp/'r97-aosp';(source/'build').mkdir(parents=True)
    (source/'build/envsetup.sh').write_text(ENVSETUP);(source/'system/core').mkdir(parents=True)
    subprocess.run(['git','init','-q',str(source/'system/core')],check=True)
    env={**os.environ,'GITHUB_WORKSPACE':str(workspace),'RUNNER_TEMP':str(temp),'R99_TEST_EVENTS':str(root/'events'),'R99_TEST_FAIL':''}
    return adapt,temp,env

def run_stage(adapt,env,*args,**overrides):
    result=subprocess.run(['bash',str(adapt/'compile.sh'),*args],env={**env,'R99_TEST_STAGE':args[0] if args else '',**overrides},capture_output=True,text=True,timeout=20)
    return result

def main():
    cases=[]
    with tempfile.TemporaryDirectory(prefix='r99-stage-tests-') as tmp:
        root=Path(tmp);adapt,temp,env=setup(root)
        for args in [(),('unknown',),('baseline','extra')]:
            assert run_stage(adapt,env,*args).returncode==2
            assert not (root/'events').exists()
        cases.append('reject_missing_unknown_or_extra_stage_before_work')
        result=run_stage(adapt,env,'baseline');assert result.returncode==0,result.stderr+result.stdout
        assert (root/'events').read_text().splitlines()==['inspect:preflight','source:baseline','m:baseline','inspect:baseline']
        cases.append('baseline_stops_before_selector_and_second_compile')
        original_preflight=(temp/'r99-evidence/toolchain-preflight.json').read_bytes()
        original_log=(temp/'r99-evidence/baseline-build.log').read_bytes()
        result=run_stage(adapt,env,'patched');assert result.returncode==0,result.stderr+result.stdout
        assert (root/'events').read_text().splitlines()[-4:]==['selector','source:patched','m:patched','inspect:patched']
        assert (temp/'r99-evidence/toolchain-preflight.json').read_bytes()==original_preflight
        assert (temp/'r99-evidence/baseline-build.log').read_bytes()==original_log
        assert (temp/'r99-evidence/patched-build.log').is_file()
        assert all((temp/'r99-evidence'/(stage+'-resources-'+when+'.txt')).is_file() for stage in ('baseline','patched') for when in ('before','after'))
        cases.append('patched_uses_preserved_baseline_and_preflight_with_separate_logs')
        for name,mutate,overrides in [
            ('missing_baseline_metadata',lambda t:(t/'r99-evidence/baseline-init.json').unlink(),{}),
            ('changed_checkpoint_binary',lambda t:(t/'r99-deliver/baseline/init').write_bytes(b'changed'),{}),
            ('changed_installed_baseline',lambda t:(t/'r97-aosp/out/target/product/sm8850/recovery/root/system/bin/init').write_bytes(b'changed'),{}),
            ('changed_toolchain',lambda t:None,{'R99_TEST_TOOLCHAIN':'changed'}),
            ('missing_original_preflight',lambda t:(t/'r99-evidence/toolchain-preflight.json').unlink(),{}),
            ('patched_source_failure',lambda t:None,{'R99_TEST_FAIL':'source:patched'}),
        ]:
            case_root=root/name;case_adapt,case_temp,case_env=setup(case_root)
            assert run_stage(case_adapt,case_env,'baseline').returncode==0
            mutate(case_temp);before=Path(case_env['R99_TEST_EVENTS']).read_text()
            result=run_stage(case_adapt,case_env,'patched',**overrides)
            assert result.returncode!=0,name
            added=Path(case_env['R99_TEST_EVENTS']).read_text()[len(before):]
            assert 'm:patched' not in added and 'inspect:patched' not in added,name
            cases.append(name+'_blocks_compile')
        for fail in ('preflight','source:baseline','compiler'):
            case_adapt,case_temp,case_env=setup(root/('fail-'+fail.replace(':','-')))
            result=run_stage(case_adapt,case_env,'baseline',R99_TEST_FAIL=fail)
            assert result.returncode!=0
            events=Path(case_env['R99_TEST_EVENTS']).read_text()
            assert 'selector' not in events and 'inspect:baseline' not in events
            if fail!='compiler':assert 'm:baseline' not in events
            cases.append(fail+'_stops_baseline')
    workflow=(HERE.parents[1]/'.github/workflows/build-myron-r99-init.yml').read_text()
    assert workflow.index('compile.sh baseline')<workflow.index('BASELINE-CHECKPOINT-NOT-FLASHABLE-')<workflow.index('compile.sh patched')
    cases.append('workflow_uploads_baseline_checkpoint_between_build_stages')
    print(json.dumps({'status':'PASS','count':len(cases),'cases':cases,'production_compile_shell_executed':True,'android_compiler_executed':False,'external_helpers_are_fixtures':True}))

if __name__=='__main__':main()
