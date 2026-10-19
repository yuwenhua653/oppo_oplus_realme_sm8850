#!/usr/bin/env python3
"""Apply only reviewed audio/display deltas after the exact R77 preparation."""
import argparse
import json
from pathlib import Path
import subprocess
from r78_inputs import check,component,parent,require,sha

def apply(workspace,repo,c,verify=False):
    check(repo,c)
    for relative,expected in c['git_heads'].items():
        actual=subprocess.check_output(['git','-C',str(workspace/relative),'rev-parse','HEAD'],text=True).strip()
        require(actual==expected,'Pinned source/toolchain HEAD mismatch: '+relative)
    # Validate both components before the first new write. A display preimage
    # mismatch must not leave the audio half applied in this fresh workspace.
    for name in ('audio','display'):
        _,_,cc=component(repo,name)
        for row in cc['writes']:
            path=workspace/row['destination']
            require(not path.is_symlink() and path.resolve().is_relative_to(workspace),'Redirected overlay destination')
            require(not path.exists() or path.is_file(),'Non-file overlay destination')
            actual=sha(path.read_bytes()) if path.exists() else None
            allowed={row['after_sha256']} if verify else {row['before_sha256'],row['after_sha256']}
            if not verify and row.get('r28_sha256'):
                allowed.add(row['r28_sha256'])
            require(actual in allowed,'Unexpected multimedia preimage: '+row['destination'])
    results={}
    for name in ('audio','display'):
        module,folder,_=component(repo,name)
        results[name]=module.apply(workspace,folder,verify=verify)
    return {'schema':1,'status':'PASS','mode':'verify' if verify else 'apply','compile_only':True,'components':results}

def verify_applied(workspace,repo,c):
    p,pc=parent(repo);_,_,foundation,prior=p.parents(repo)
    inherited=json.loads((repo/pc['base_contract']).read_text())
    expected={r['path']:r['sha256'] for r in inherited['workspace_files']}
    expected.update({r['destination']:r['after_sha256'] for r in prior['writes']+foundation['writes']+pc['writes']})
    for name in ('audio','display'):
        _,_,cc=component(repo,name)
        expected.update({r['destination']:r['after_sha256'] for r in cc['writes']})
    for relative,digest in expected.items():
        f=workspace/relative
        require(f.is_file() and not f.is_symlink() and f.resolve().is_relative_to(workspace),'Missing/redirected integrated file: '+relative)
        require(sha(f.read_bytes())==digest,'Integrated postimage changed: '+relative)
    return {'status':'PASS','checked_destinations':len(expected)}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path,required=True);p.add_argument('--repo-root',type=Path,required=True);p.add_argument('--check',action='store_true');a=p.parse_args()
    repo=a.repo_root.resolve();w=a.workspace.resolve();c=json.loads((repo/'r78-build-route/multimedia-contract.json').read_text())
    print(json.dumps(apply(w,repo,c,verify=a.check),indent=2))
