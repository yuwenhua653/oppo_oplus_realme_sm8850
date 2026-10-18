#!/usr/bin/env python3
"""Plan final bytes for all eleven inherited/new destinations before mutation."""
import argparse
import json
from pathlib import Path
import subprocess
from thermal_inputs import check, parents, overlay_bytes

def plan(workspace,repo,c,verify=False):
    check(repo,c)
    _,checker,parent,prior=parents(repo)
    for relative,expected in c['git_heads'].items():
        actual=subprocess.check_output(['git','-C',str(checker.safe(workspace,relative,exists=False)),'rev-parse','HEAD'],text=True).strip()
        checker.require(actual==expected,'Source/toolchain HEAD mismatch: '+relative)
    desired={}
    for row in prior['writes']+parent['writes']:
        desired[row['destination']]={'data':checker.overlay_bytes(repo,row),'allowed':{row['before_sha256'],row['after_sha256']}}
    for row in c['writes']:
        old=desired.get(row['destination'])
        allowed=old['allowed']|{row['after_sha256']} if old else {row['before_sha256'],row['after_sha256']}
        desired[row['destination']]={'data':overlay_bytes(repo,row),'allowed':allowed}
    checker.require(len(desired)==11,'Unexpected combined destination count')
    pending=[]
    for relative,row in desired.items():
        p=checker.safe(workspace,relative,exists=False)
        checker.require(not p.exists() or p.is_file(),'Non-file overlay destination')
        actual=checker.sha(p.read_bytes()) if p.exists() else None
        expected=checker.sha(row['data'])
        checker.require(actual in row['allowed'],'Unexpected layered preimage: '+relative)
        checker.require(not verify or actual==expected,'Final R77 overlay not applied: '+relative)
        pending.append((p,row['data'],actual!=expected))
    return pending

def apply(workspace,repo,c,verify=False):
    pending=plan(workspace,repo,c,verify);_,checker,_,_=parents(repo)
    if not verify:
        for p,data,changed in pending:
            if changed:
                p.parent.mkdir(parents=True,exist_ok=True);temporary=p.with_name(p.name+'.r77-tmp')
                with temporary.open('xb') as stream:stream.write(data)
                temporary.replace(p)
    return {'schema':1,'status':'PASS','compile_only':True,'mode':'verify' if verify else 'apply',
            'writes':[{'path':str(p.relative_to(workspace)),'sha256':checker.sha(data),'changed':changed} for p,data,changed in pending]}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo-root',required=True,type=Path)
    p.add_argument('--workspace',required=True,type=Path);p.add_argument('--check',action='store_true');args=p.parse_args()
    repo=args.repo_root.resolve();workspace=args.workspace.resolve()
    print(json.dumps(apply(workspace,repo,json.loads((repo/'r77-build-route/thermal-contract.json').read_text()),args.check),indent=2))
