#!/usr/bin/env python3
"""Build explicit R79 repair targets from the retained R78 source preparation."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from r79_inputs import check,parent,require,safe,sha,load,PARENT
from apply_repairs import apply,verify_applied
resolve = load('r79_output_resolver', Path(__file__).resolve().parents[1] / 'r78-build-route/resolve_outputs.py').resolve

def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,indent=2)+'\n')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','package','baseline','r18','repo-root'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--jobs',type=int,default=2)
    parser.add_argument('--ram-mb',type=int,default=10000,help='Bazel local RAM budget; use 6144 on an 8 GiB build host')
    args=parser.parse_args()
    root,package,baseline,r18,repo=[getattr(args,n).resolve() for n in ('workspace','package','baseline','r18','repo_root')]
    reports=root/'integration-reports';output=root/'integration-artifacts/r79-targeted-repairs'
    cp=repo/'r79-build-route/repair-contract.json';sp=reports/'r79-status.json'
    status={'schema':1,'success':False,'compile_only':True,'flashable':False,'hardware_tested':False,'runtime_abi_compatible':'NOT_YET_VALIDATED',
            'github':{k:os.environ.get(k,'') for k in ('GITHUB_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT')},'phase':'preflight',
            'started_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    write(sp,status)
    try:
        require(1<=args.jobs<=4 and args.ram_mb>=2048,'Invalid build resource budget');require(not output.exists() and not output.is_symlink(),'Use a fresh CI artifact destination')
        c=json.loads(cp.read_text());check(repo,c);status['source_contract_sha256']=sha(cp.read_bytes())
        p,pc=parent(repo); thermal,tc=p.parent(repo);inherited=json.loads((repo/tc['base_contract']).read_text())
        sys.path.insert(0,str(repo/'r61-build-route'));shared=load('r79_shared',repo/'r61-build-route/targeted_battery_build.py')
        old=load('r79_r18',r18/'boot_build.py');status['r18_bundle_lock_sha256']=old.verify_bundle()
        helper=load('r79_driver',baseline/'drivers/driver_check.py')
        runner_data,status['baseline_runner']=helper.verify_bundle(baseline,package/'build_platform.py')
        require(sha((package/'sources.lock.json').read_bytes())==c['sources_lock_sha256'],'Sources lock mismatch')
        bazel,options=helper.runner_build_configuration(runner_data,root,args.jobs,args.ram_mb)
        status['resource_budget']={'jobs':args.jobs,'ram_mb':args.ram_mb}
        # Do not continue the expensive kernel build after a prerequisite fails.
        options=list(options)+['--nokeep_going']
        runner=load('r79_platform',package/'build_platform.py')
        def logged(command,name):runner.logged(command,root,reports/('r79-'+name+'.log'))
        status['phase']='prepare_exact_sources';write(sp,status)
        logged([sys.executable,str(package/'prepare_workspace.py'),'--workspace',str(root)],'prepare')
        logged([sys.executable,str(baseline/'run_r12.py'),'apply','--workspace',str(root),'--stage','soc'],'r13-apply')
        helper.verify_applied_writes(baseline,root)
        hardware=json.loads((repo/inherited['prerequisite_contract']).read_text())
        for name,sc in [('r60',hardware),('r61',inherited)]:
            command=[sys.executable,str(repo/sc['integration']['script']),'--workspace',str(root)]
            logged(command,name+'-apply');logged(command+['--check'],name+'-check');shared.locked_workspace(root,sc['workspace_files'])
        from apply_thermal import apply as apply_parent
        write(reports/'r79-parent-apply.json',apply_parent(root,repo,tc))
        write(reports/'r79-parent-check.json',apply_parent(root,repo,tc,verify=True))
        from apply_multimedia import apply as apply_multimedia
        write(reports/'r79-retained-r78-apply.json',apply_multimedia(root,repo,pc))
        write(reports/'r79-retained-r78-check.json',apply_multimedia(root,repo,pc,verify=True))
        write(reports/'r79-overlay-apply.json',apply(root,repo,c))
        write(reports/'r79-overlay-check.json',apply(root,repo,c,verify=True))
        write(reports/'r79-source-postimages.json',verify_applied(root,repo,c))
        runner.build_targets(root,'soc')  # Emit release metadata only, never select the old aggregate.
        targets=[m['target'] for m in c['modules']]+c['core_targets']
        require(len(targets)==len(set(targets)),'Duplicate selected targets')
        plan={'kconfig':bazel+['build']+options+['//vendor/qcom/sm8850:kconfig.msm.generated'],
              'build':bazel+['build']+options+targets,
              'cquery':bazel+['cquery']+options+['--output=files','deps(set('+' '.join(targets)+'))']}
        write(reports/'r79-commands.json',plan)
        status.update(phase='analyze_repair_targets',explicit_build_targets=targets);write(sp,status)
        command=bazel+['aquery']+options+['--output=jsonproto','--include_artifacts=true','--include_commandline=true','deps(set('+' '.join(m['target'] for m in c['modules'])+'))']
        result=subprocess.run(command,cwd=root,text=True,capture_output=True)
        (reports/'r79-aquery.json').write_text(result.stdout);(reports/'r79-aquery.log').write_text(result.stderr)
        require(result.returncode==0,'aquery failed before compilation')
        graph=json.loads(result.stdout);selected=[resolve(graph,m) for m in c['modules']]
        write(reports/'r79-actual-target-outputs.json',{'schema':1,'modules':selected})
        for row in selected:
            write(reports/('r79-action-'+row['module_name']+'.json'),shared.action_chain(graph,row['expected_sources'],row['output']))
        # aquery does not execute genrules. Resolve all external Kconfig sources
        # before starting the kernel and module compilation actions.
        status['phase']='generate_external_kconfig';write(sp,status)
        logged(plan['kconfig'],'kconfig-build')
        status['phase']='compile_repairs_and_required_dependencies';write(sp,status)
        logged(plan['build'],'build')
        result=subprocess.run(plan['cquery'],cwd=root,text=True,capture_output=True)
        (reports/'r79-cquery.txt').write_text(result.stdout);(reports/'r79-cquery.log').write_text(result.stderr)
        require(result.returncode==0,'cquery failed after build');verify_applied(root,repo,c)
        status['phase']='collect_verified_outputs';write(sp,status)
        status.update(shared.collect_outputs(root,output,c,selected,result.stdout.splitlines(),r18))
        require(json.loads((output/'module-inventory.json').read_text())['module_count']==len(c['selected_module_names']),'Actual KO count differs from frozen repair target inventory')
        status.update(success=True,compiled=True,phase='compiled_source_bound_not_runtime_approved',
                      limitation='The R78 Runtime Fix1 image remains authoritative. Output modules require full installed-kernel ABI and owner/policy checks before runtime selection. A compiled charging module alone does not establish fast charging.')
        write(sp,status)
        shutil.copy2(cp,output/'repair-contract.json');shutil.copy2(repo/PARENT,output/'parent-r78-contract.json')
        (output/'reports').mkdir()
        for report in sorted(reports.glob('r79-*')):
            if report.is_file():shutil.copy2(report,output/'reports'/report.name)
        write(output/'artifact-lock.json',{'schema':1,'compile_only':True,'files':[
            {'file':str(p.relative_to(output)),'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in sorted(output.rglob('*')) if p.is_file()]})
        write(output/'candidate-complete.json',{'schema':1,'compile_only':True,'flashable':False,'required_module_count':len(c['selected_module_names']),
              'runtime_abi_compatible':'NOT_YET_VALIDATED','artifact_lock_sha256':sha((output/'artifact-lock.json').read_bytes()),'source_contract_sha256':status['source_contract_sha256']})
    except Exception as error:
        status.update(success=False,error=str(error));print('R79 STOP:',error,file=sys.stderr)
    finally:
        status['finished_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());write(sp,status)
    return 0 if status['success'] else 1

if __name__=='__main__':sys.exit(main())
