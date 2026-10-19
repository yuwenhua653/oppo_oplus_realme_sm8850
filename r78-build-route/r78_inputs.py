#!/usr/bin/env python3
"""Check the immutable R77 parent and all new multimedia source inputs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import sys

PARENT='r77-build-route/thermal-contract.json'
PARENT_SHA='0b3ef93711b68d6db422d5b0f1d86974985b31bc7034c8c36fa59a012c86498f'
BASE_COMMIT='01845c8dcdbc7a5c42f8037f4839e4b12e61137f'
def require(ok, message):
    if not ok: raise ValueError(message)
def sha(data): return hashlib.sha256(data).hexdigest()
def safe(root, relative):
    p=PurePosixPath(relative)
    require(relative and not p.is_absolute() and '..' not in p.parts, 'Unsafe path: '+relative)
    f=root/p
    require(not f.is_symlink() and f.is_file() and f.resolve().is_relative_to(root.resolve()), 'Missing/redirected input: '+relative)
    return f
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def parent(repo):
    require(sha(safe(repo,PARENT).read_bytes())==PARENT_SHA,'R77 source contract changed')
    sys.path.insert(0,str(repo/'r77-build-route'))
    import thermal_inputs
    c=json.loads((repo/PARENT).read_text())
    return thermal_inputs,c
def component(repo,name):
    folder=repo/'r78-build-route'/name
    return load('r78_'+name+'_apply',folder/'apply.py'),folder,json.loads((folder/'contract.json').read_text())
def check(repo,c):
    require(c.get('schema')==1 and c.get('base_commit')==BASE_COMMIT,'Unexpected R78 base')
    require(c.get('compile_only') is True and c.get('flashable') is False and c.get('runtime_changes')==[],'Compile-only scope changed')
    p,pc=parent(repo);p.check(repo,pc)
    for k in ('baseline_image_sha256','baseline_kernel_release','sources_lock_sha256','git_heads','core_targets'):
        require(c.get(k)==pc[k],'Preserved preparation identity changed: '+k)
    require(c.get('parent_contract')==PARENT and c.get('parent_contract_sha256')==PARENT_SHA,'Parent pin changed')
    rows=c['locked_files']; names=[r['path'] for r in rows]
    require(len(names)==len(set(names)),'Duplicate new input')
    own={str(p.relative_to(repo)) for p in (repo/'r78-build-route').rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='multimedia-contract.json'}
    require(set(names)==own,'Unpinned or unexpected R78 file')
    for row in rows:
        data=safe(repo,row['path']).read_bytes()
        require(len(data)==row['bytes'] and sha(data)==row['sha256'],'R78 input mismatch: '+row['path'])
    modules=[];writes=[]
    for name in ('audio','display'):
        module,folder,cc=component(repo,name)
        module.check(folder)
        modules.extend(cc['modules'] if 'modules' in cc else [cc['module']]);writes.extend(cc['writes'])
    require(c['modules']==modules,'Selected target/source descriptions changed')
    require(c.get('selected_module_names')==[m['module_name'] for m in modules],'Frozen module inventory changed')
    require({'tfa98xx_dlkm','msm_drm'} <= set(c['selected_module_names']),'Audio and display targets must both be selected')
    require(len(c['selected_module_names'])==len(set(c['selected_module_names'])),'Duplicate selected module name')
    destinations=[r['destination'] for r in writes]
    require(len(destinations)==len(set(destinations)),'Audio/display writes overlap')
    return {'schema':1,'status':'PASS','compile_only':True,'flashable':False,'locked_inputs':len(rows),'selected_modules':[m['module_name'] for m in modules],'parent_unchanged':True,'runtime_changes':[]}

if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--root',type=Path,required=True);args=a.parse_args();root=args.root.resolve()
    print(json.dumps(check(root,json.loads((root/'r78-build-route/multimedia-contract.json').read_text())),indent=2))
