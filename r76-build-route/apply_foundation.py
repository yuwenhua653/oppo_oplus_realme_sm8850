#!/usr/bin/env python3
"""Plan every R75 and R76 write before changing any integrated source."""
import argparse
import json
from pathlib import Path
from foundation_inputs import check, parent_modules, PARENT

def plan(workspace,repo,contract,verify=False):
    check(repo,contract)
    checker,prior=parent_modules(repo)
    parent=json.loads((repo/PARENT).read_text())
    pending=prior.plan(workspace,repo,parent,verify)
    for row in contract['writes']:
        path=checker.safe(workspace,row['destination'],exists=False)
        checker.require(path.is_file(),'Missing R76 source preimage')
        current=checker.sha(path.read_bytes())
        checker.require(current in (row['before_sha256'],row['after_sha256']), 'Unexpected R76 preimage: '+row['destination'])
        checker.require(not verify or current==row['after_sha256'], 'R76 overlay not applied')
        pending.append((path,checker.overlay_bytes(repo,row),current!=row['after_sha256']))
    return pending

def apply(workspace,repo,contract,verify=False):
    pending=plan(workspace,repo,contract,verify)
    checker,_=parent_modules(repo)
    if not verify:
        for path,data,changed in pending:
            if changed:
                path.parent.mkdir(parents=True,exist_ok=True)
                temporary=path.with_name(path.name+'.r76-tmp')
                with temporary.open('xb') as stream:stream.write(data)
                temporary.replace(path)
    return {'schema':1,'status':'PASS','compile_only':True,'mode':'verify' if verify else 'apply',
            'writes':[{'path':str(p.relative_to(workspace)),'sha256':checker.sha(data),'changed':changed} for p,data,changed in pending]}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root',type=Path,required=True);parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--check',action='store_true');args=parser.parse_args()
    repo=args.repo_root.resolve();workspace=args.workspace.resolve()
    print(json.dumps(apply(workspace,repo,json.loads((repo/'r76-build-route/foundation-contract.json').read_text()),args.check),indent=2))
