#!/usr/bin/env python3
"""One source-locked compile of the TFA and display candidates; no device image."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from r78_inputs import check,parent,require,safe,sha,load,PARENT
from apply_multimedia import apply,verify_applied
from resolve_outputs import resolve

def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,indent=2)+'\n')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','package','baseline','r18','repo-root'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--jobs',type=int,default=2);args=parser.parse_args()
    root,package,baseline,r18,repo=[getattr(args,n).resolve() for n in ('workspace','package','baseline','r18','repo_root')]
    reports=root/'integration-reports';output=root/'integration-artifacts/r78-targeted-multimedia'
    cp=repo/'r78-build-route/multimedia-contract.json';sp=reports/'r78-status.json'
    status={'schema':1,'success':False,'compile_only':True,'flashable':False,'hardware_tested':False,'runtime_abi_compatible':'NOT_YET_VALIDATED',
            'github':{k:os.environ.get(k,'') for k in ('GITHUB_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT')},'phase':'preflight',
            'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    write(sp,status)
    try:
        require(1<=args.jobs<=4,'Invalid job count');require(not output.exists() and not output.is_symlink(),'Use a fresh CI artifact destination')
        c=json.loads(cp.read_text());check(repo,c);status['source_contract_sha256']=sha(cp.read_bytes())
        p,pc=parent(repo);inherited=json.loads((repo/pc['base_contract']).read_text())
        sys.path.insert(0,str(repo/'r61-build-route'));shared=load('r78_shared',repo/'r61-build-route/targeted_battery_build.py')
        old=load('r78_r18',r18/'boot_build.py');status['r18_bundle_lock_sha256']=old.verify_bundle()
        helper=load('r78_driver',baseline/'drivers/driver_check.py')
        runner_data,status['baseline_runner']=helper.verify_bundle(baseline,package/'build_platform.py')
        require(sha((package/'sources.lock.json').read_bytes())==c['sources_lock_sha256'],'Sources lock mismatch')
        bazel,options=helper.runner_build_configuration(runner_data,root,args.jobs,10000)
        runner=load('r78_platform',package/'build_platform.py')
        def logged(command,name):runner.logged(command,root,reports/('r78-'+name+'.log'))
        status['phase']='prepare_exact_sources';write(sp,status)
        logged([sys.executable,str(package/'prepare_workspace.py'),'--workspace',str(root)],'prepare')
        logged([sys.executable,str(baseline/'run_r12.py'),'apply','--workspace',str(root),'--stage','soc'],'r13-apply')
        helper.verify_applied_writes(baseline,root)
        hardware=json.loads((repo/inherited['prerequisite_contract']).read_text())
        for name,sc in [('r60',hardware),('r61',inherited)]:
            command=[sys.executable,str(repo/sc['integration']['script']),'--workspace',str(root)]
            logged(command,name+'-apply');logged(command+['--check'],name+'-check');shared.locked_workspace(root,sc['workspace_files'])
        from apply_thermal import apply as apply_parent
        write(reports/'r78-parent-apply.json',apply_parent(root,repo,pc))
        write(reports/'r78-parent-check.json',apply_parent(root,repo,pc,verify=True))
        write(reports/'r78-overlay-apply.json',apply(root,repo,c))
        write(reports/'r78-overlay-check.json',apply(root,repo,c,verify=True))
        write(reports/'r78-source-postimages.json',verify_applied(root,repo,c))
        runner.build_targets(root,'soc')  # Emit release metadata only, never select the old aggregate.
        targets=[m['target'] for m in c['modules']]+c['core_targets']
        require(len(targets)==len(set(targets)),'Duplicate selected targets')
        plan={'build':bazel+['build']+options+targets,
              'cquery':bazel+['cquery']+options+['--output=files','deps(set('+' '.join(targets)+'))']}
        write(reports/'r78-commands.json',plan)
        status.update(phase='analyze_audio_and_display',explicit_build_targets=targets);write(sp,status)
        command=bazel+['aquery']+options+['--output=jsonproto','--include_artifacts=true','--include_commandline=true','deps(set('+' '.join(m['target'] for m in c['modules'])+'))']
        result=subprocess.run(command,cwd=root,text=True,capture_output=True)
        (reports/'r78-aquery.json').write_text(result.stdout);(reports/'r78-aquery.log').write_text(result.stderr)
        require(result.returncode==0,'aquery failed before compilation')
        graph=json.loads(result.stdout);selected=[resolve(graph,m) for m in c['modules']]
        write(reports/'r78-actual-target-outputs.json',{'schema':1,'modules':selected})
        for row in selected:
            write(reports/('r78-action-'+row['module_name']+'.json'),shared.action_chain(graph,row['expected_sources'],row['output']))
        status['phase']='compile_audio_display_and_required_dependencies';write(sp,status)
        logged(plan['build'],'build')
        result=subprocess.run(plan['cquery'],cwd=root,text=True,capture_output=True)
        (reports/'r78-cquery.txt').write_text(result.stdout);(reports/'r78-cquery.log').write_text(result.stderr)
        require(result.returncode==0,'cquery failed after build');verify_applied(root,repo,c)
        status['phase']='collect_verified_outputs';write(sp,status)
        status.update(shared.collect_outputs(root,output,c,selected,result.stdout.splitlines(),r18))
        require(json.loads((output/'module-inventory.json').read_text())['module_count']==len(c['selected_module_names']),'Actual KO count differs from frozen audio/display target inventory')
        status.update(success=True,compiled=True,phase='compiled_source_bound_not_runtime_approved',
                      limitation='The retained R75 kernel and modules remain authoritative. New audio/display runtime compatibility and firmware/machine mapping are evaluated from actual outputs before assembly.')
        write(sp,status)
        shutil.copy2(cp,output/'multimedia-contract.json');shutil.copy2(repo/PARENT,output/'parent-r77-contract.json')
        (output/'reports').mkdir()
        for report in sorted(reports.glob('r78-*')):
            if report.is_file():shutil.copy2(report,output/'reports'/report.name)
        write(output/'artifact-lock.json',{'schema':1,'compile_only':True,'files':[
            {'file':str(p.relative_to(output)),'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in sorted(output.rglob('*')) if p.is_file()]})
        write(output/'candidate-complete.json',{'schema':1,'compile_only':True,'flashable':False,'required_module_count':len(c['selected_module_names']),
              'runtime_abi_compatible':'NOT_YET_VALIDATED','artifact_lock_sha256':sha((output/'artifact-lock.json').read_bytes()),'source_contract_sha256':status['source_contract_sha256']})
    except Exception as error:
        status.update(success=False,error=str(error));print('R78 STOP:',error,file=sys.stderr)
    finally:
        status['finished_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());write(sp,status)
    return 0 if status['success'] else 1

if __name__=='__main__':sys.exit(main())
