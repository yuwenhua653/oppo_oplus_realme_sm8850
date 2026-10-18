#!/usr/bin/env python3
"""Verify exact R76 preparation and the standalone R77 observer build overlay."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import sys

PARENT='r76-build-route/foundation-contract.json'
PARENT_SHA='e2eef12cfc674435a85e5f3c92355353be2daf49cf27c65a9ec0f8f40e27deac'
BASE_COMMIT='513e1f19a44dd67f127999dfa27f77ac88e70f49'
VENDOR='vendor/qcom/sm8850/'
STEM='drivers/thermal/myron_buck_thermal'
SOURCE='r77-build-route/payload/'+STEM+'.c'
APPENDS={VENDOR+'drivers/xiaomi/myron/Kconfig':'r77-build-route/fragments/Kconfig',
         VENDOR+'drivers/xiaomi/myron/modules.bzl':'r77-build-route/fragments/modules.bzl',
         VENDOR+'configs/canoe_perf.bzl':'r77-build-route/fragments/canoe_perf.bzl'}
OWN_INPUTS={'r77-build-route/'+n for n in ('README.md','thermal_inputs.py','apply_thermal.py','build_thermal.py',
 'run_host_tests.py','test_integration.py','fragments/Kconfig','fragments/modules.bzl','fragments/canoe_perf.bzl',
 'tests/run_tests.py','tests/fake_kernel.h','tests/test_receiver.c','receiver-contract.json')}|{SOURCE}
READONLY_KO_PINS={
 'qti_pmic_glink':{'bytes':46960,'sha256':'29f97959761de3f2145c5bd8f8a6ef3b1bc1e18196f0c99b3bfbc6b94410aa86'},
 'myron_mca_readonly':{'bytes':39152,'sha256':'5d336da04be43186f696e1d62b3de4d27727942471e6d58d480173eda9c72f8f'},
 'myron_bq_readonly':{'bytes':20376,'sha256':'924d7e337ba8b5e7270f9a98352d15793eebab90604afde11c874a03423d8a91'}}

def check_fragments(kconfig,registration,selection):
    """Validate the real build wiring without executing Starlark/Python text."""
    def need(ok,why):
        if not ok:raise ValueError(why)
    block=ast.parse('def register_modules(registry):\n'+registration).body[0].body
    need(len(block)==1 and isinstance(block[0],ast.Expr) and isinstance(block[0].value,ast.Call),'Exactly one new DDK registration')
    call=block[0].value
    need(isinstance(call.func,ast.Attribute) and isinstance(call.func.value,ast.Name) and
         call.func.value.id=='registry' and call.func.attr=='register' and not call.args,'Expected DDK registry.register')
    values={k.arg:ast.literal_eval(k.value) for k in call.keywords}
    need(len(values)==len(call.keywords) and values=={'name':STEM,'out':'myron_buck_thermal.ko',
         'config':'CONFIG_MYRON_BUCK_THERMAL','srcs':[STEM+'.c'],'deps':[]},'Exact standalone observer DDK mapping')
    lines=[l.strip() for l in kconfig.splitlines() if l.strip()]
    need([l for l in lines if l.startswith('config ')]==['config MYRON_BUCK_THERMAL'] and
         [l for l in lines if l.startswith('depends on ')]==['depends on OF && SYSFS'] and
         [l for l in lines if l.startswith('default ')]==['default n'],'Observer Kconfig must remain default n, OF/SYSFS only')
    body=ast.parse(selection).body
    need(len(body)==1 and isinstance(body[0],ast.Assign) and len(body[0].targets)==1,'One target-local config selection')
    node=body[0];target=node.targets[0]
    need(isinstance(target,ast.Subscript) and isinstance(target.value,ast.Name) and target.value.id=='canoe_perf_config' and
         ast.literal_eval(target.slice)=='CONFIG_MYRON_BUCK_THERMAL' and ast.literal_eval(node.value)=='m',
         'Observer build selection must be exactly m')

def parents(root):
    pins={PARENT:PARENT_SHA,'r76-build-route/foundation_inputs.py':'56abde99c861dc0add292734e2cbb9b28e1120a55f6a25a2ed15191caad3f33e'}
    for n,digest in pins.items():
        p=root/n
        if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()) or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
            raise ValueError('Untrusted R76 bootstrap: '+n)
    sys.path.insert(0,str(root/'r76-build-route'))
    import foundation_inputs as foundation
    prior_check,_=foundation.parent_modules(root)
    parent=json.loads((root/PARENT).read_text())
    prior=json.loads((root/foundation.PARENT).read_text())
    return foundation,prior_check,parent,prior

def overlay_bytes(root,row):
    _,checker,_,prior=parents(root)
    data=checker.safe(root,row['source']).read_bytes()
    if row['mode']=='append_parent':
        old=next(r for r in prior['writes'] if r['destination']==row['destination'])
        previous=checker.overlay_bytes(root,old)
        checker.require(checker.sha(previous)==row['before_sha256'],'R77 append parent postimage changed')
        data=previous+data
    else:checker.require(row['mode']=='replace','Unknown R77 operation')
    checker.require(checker.sha(data)==row['after_sha256'] and len(data)==row['bytes'],'R77 derived postimage mismatch')
    return data

def check(root,c,inherited=True):
    foundation,checker,parent,prior=parents(root)
    need,safe,sha=checker.require,checker.safe,checker.sha
    need(c.get('schema')==1 and c.get('source_review')=='PASS','R77 source review incomplete')
    need(c.get('base_commit')==BASE_COMMIT,'R77 base commit changed')
    need(c.get('compile_only') is True and c.get('flashable') is False and c.get('runtime_changes')==[],'R77 remains compile-only')
    need(c.get('parent_contract')==PARENT and c.get('parent_contract_sha256')==PARENT_SHA,'R76 parent identity changed')
    foundation.check(root,parent,inherited=inherited)
    for k in ('base_contract','base_contract_sha256','baseline_image_sha256','baseline_kernel_release','sources_lock_sha256','git_heads','core_targets'):
        need(c.get(k)==parent[k],'Frozen preparation identity changed: '+k)
    locked={r['path']:r for r in c.get('locked_files',[])}
    inherited_pins={r['path']:r for r in parent['locked_files']}
    inherited_pins[PARENT]={'path':PARENT,'bytes':safe(root,PARENT).stat().st_size,'sha256':PARENT_SHA}
    need(len(locked)==len(c.get('locked_files',[])),'Duplicate R77 source lock')
    need(set(locked)==set(inherited_pins)|OWN_INPUTS,'R77 locked input scope changed')
    need(all(locked[n]==v for n,v in inherited_pins.items()),'Inherited R76 source pins changed')
    for n,r in locked.items():
        data=safe(root,n).read_bytes();need(len(data)==r['bytes'] and sha(data)==r['sha256'],'R77 input bytes changed: '+n)
    actual={str(p.relative_to(root)) for p in (root/'r77-build-route').rglob('*') if p.is_file() and p.name!='thermal-contract.json' and '__pycache__' not in p.parts}
    need(actual==OWN_INPUTS,'R77 upload inventory changed')
    writes=c.get('writes',[])
    need(len(writes)==4 and {r['destination'] for r in writes}==set(APPENDS)|{VENDOR+STEM+'.c'},'Only four R77 operations allowed')
    for row in writes:
        if row['destination'] in APPENDS:
            old=next(r for r in prior['writes'] if r['destination']==row['destination'])
            need(row['mode']=='append_parent' and row['source']==APPENDS[row['destination']] and row['before_sha256']==old['after_sha256'],'Exact parent append required')
        else:
            need(row['mode']=='replace' and row['source']==SOURCE and row['before_sha256'] is None,'Only new independent observer source allowed')
        need(row['source'] in locked,'Unpinned R77 postimage source');overlay_bytes(root,row)
    modules=c.get('modules',[])
    need(len(modules)==4 and modules[:3]==prior['modules'],'Exactly three frozen readonly targets and new observer required')
    prefix='bazel-out/aarch64-fastbuild/bin/vendor/qcom/sm8850/canoe_perf/'+STEM+'/'
    need(modules[3]=={'module_name':'myron_buck_thermal','stem':STEM,'target':'//vendor/qcom/sm8850:canoe_perf/'+STEM,
                     'output':prefix+'myron_buck_thermal.ko','symvers':prefix+'canoe_perf/'+STEM+'_Module.symvers',
                     'expected_sources':[VENDOR+STEM+'.c']},'Observer source/target mapping changed')
    need(c.get('not_rebuilt_foundation_targets')==['mca_adsp_glink','mca_qcom_subpmic_proxy','mca_strategy_buckchg'], 'Unchanged foundation targets must not be claimed as R77 outputs')
    need(c.get('unchanged_readonly_KOs')==READONLY_KO_PINS,'Existing readonly KO byte pins changed')
    check_fragments(*(safe(root,'r77-build-route/fragments/'+n).read_text() for n in ('Kconfig','modules.bzl','canoe_perf.bzl')))
    tokens=checker.header_tokens(safe(root,SOURCE).read_bytes())
    receiver=safe(root,'r77-build-route/receiver-contract.json')
    need(sha(receiver.read_bytes())=='552a725a1e3b617de89705abc2c18e9f6c2d20bcc898df48cc61100ee4beefa0','Frozen receiver behavior contract changed')
    behavior=json.loads(receiver.read_text())
    need(behavior['production_source']['sha256']==sha(safe(root,SOURCE).read_bytes()) and
         behavior['compile_only'] is True and behavior['runtime_loading_approved'] is False,'Receiver behavior/source mismatch')
    need(re.findall(r'module_param\(([^,]+),([^,]+),([^\)]+)\);',tokens)==[('enable_observer','bool','0444')], 'Exact observer boolean parameter required')
    need(len(re.findall(r'staticboolenable_observer(?:=false)?;',tokens))==1,'Observer must default off')
    need(not re.search(r'EXPORT_SYMBOL(?:_GPL|_NS|_NS_GPL)?\(',tokens),'Observer cannot export private kernel interfaces')
    fixture=safe(root,'r77-build-route/tests/fake_kernel.h').read_text()
    runner=safe(root,'r77-build-route/tests/run_tests.py').read_text()
    need('#define current get_current()' in fixture and '-Wstrict-prototypes' in runner,'Kernel current macro and strict prototypes guards required')
    return {'schema':1,'status':'PASS','compile_only':True,'flashable':False,'locked_files':len(locked),'own_inputs':len(OWN_INPUTS),
            'new_overlay_operations':4,'distinct_workspace_destinations':11,'modules':[r['module_name'] for r in modules],
            'foundation_MCA_targets_rebuilt':False,'runtime_abi_compatible':'NOT_YET_VALIDATED'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True,type=Path);args=p.parse_args()
    root=args.root.resolve();print(json.dumps(check(root,json.loads((root/'r77-build-route/thermal-contract.json').read_text())),indent=2))
