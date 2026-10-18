#!/usr/bin/env python3
"""Verify a narrow R76 overlay on the immutable R75/R61 preparation."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

PARENT = 'r75-build-route/charge-contract.json'
PARENT_SHA = 'd191be88cb0fb978e54becb894cceaa27a0c02962eafe99ddbe5711862d34d56'
BASE_COMMIT = '07201ea64edafef3ef3841e6386aba400ec4ca65'
VENDOR = 'vendor/qcom/sm8850/'
STEMS = {
 'mca_adsp_glink': 'drivers/power/supply/mca/mca_common/mca_adsp_glink',
 'mca_qcom_subpmic_proxy': 'drivers/power/supply/mca/mca_qcom_subpmic_proxy/mca_qcom_subpmic_proxy',
 'mca_strategy_buckchg': 'drivers/power/supply/mca/mca_strategy/strategy_charger/mca_strategy_buckchg',
}
PINS = {
 'mca_adsp_glink': ('02ee6caf120a010e712480e4b655376aff62183776f226b9f82dd69d37b7a8b9', 'b766aba518a331a2833f40caa402bfb767f59149e8c593699a27d14034115df5'),
 'mca_qcom_subpmic_proxy': ('305f85f59082d8a2326a34c9075969247e79901c5868986fa287bd88a59d5fbc', '721a6bd66e2e03c70673ae35298171667cc516006ffbfd3727a4d8bf1ae06e19'),
 'mca_strategy_buckchg': ('cb1f328ae9107ce6deb6e1f89f2f21710bd5f392940f61cfebefe8501c2e6e66', 'd30335d6bbc64e522c28fe799d41ecd0946688f4654ca86ff94a88165a6c54b7'),
}
OWN_INPUTS = {'r76-build-route/'+n for n in (
 'README.md','foundation_inputs.py','apply_foundation.py','build_foundation.py',
 'run_host_tests.py','test_integration.py','reference/mca_adsp_glink.h',
 'tests/mca_transport/run_tests.py','tests/mca_transport/test_transport.c','tests/mca_transport/fake_kernel.h',
 'tests/control/run_extracted_tests.py','tests/control/setters_harness.c','tests/control/probe_harness.c',
)} | {'r76-build-route/payload/'+s+'.c' for s in STEMS.values()}

def parent_modules(root):
    # The imported parent directory is immutable and validated before use.
    bootstrap={PARENT:PARENT_SHA,
      'r75-build-route/check_charge_inputs.py':'d98f2e8738de3e7e006d7f05d80117db4aebd5a54a80e0da2a425416f24d25a2',
      'r75-build-route/apply_charge.py':'c9c042055e18d3058c63bcfbcbe31e050bfddccfcf7dbf9b3e4bfa429beccba8',
      'r75-build-route/build_charge.py':'8098992588262984d8272672d34c87acca3cc61f2d7ad5c105454d10b55b43ce'}
    for relative,digest in bootstrap.items():
        p=root/relative
        if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()) or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
            raise ValueError('Untrusted R75 bootstrap: '+relative)
    sys.path.insert(0, str(root/'r75-build-route'))
    import check_charge_inputs as checker
    import apply_charge as overlay
    return checker, overlay

def check(root, contract, inherited=True):
    parent_check, _ = parent_modules(root)
    require, safe, sha = parent_check.require, parent_check.safe, parent_check.sha
    require(contract.get('schema') == 1 and contract.get('source_review') == 'PASS', 'R76 source review incomplete')
    require(contract.get('base_commit') == BASE_COMMIT, 'R76 remote base changed')
    require(contract.get('compile_only') is True and contract.get('flashable') is False and
            contract.get('runtime_changes') == [], 'R76 is compile-only with no runtime changes')
    require(contract.get('parent_contract') == PARENT and contract.get('parent_contract_sha256') == PARENT_SHA,
            'R75 parent identity changed')
    require(sha(safe(root,PARENT).read_bytes()) == PARENT_SHA, 'R75 parent bytes changed')
    parent = json.loads(safe(root,PARENT).read_text())
    parent_check.check(root,parent) if inherited else parent_check.check_overlay(root,parent)
    for key in ('base_contract','base_contract_sha256','baseline_image_sha256','baseline_kernel_release',
                'sources_lock_sha256','git_heads','core_targets'):
        require(contract.get(key) == parent[key], 'Inherited build identity changed: '+key)
    inherited_pins={r['path']:r for r in parent['locked_files']}
    inherited_pins[PARENT]={'path':PARENT,'bytes':safe(root,PARENT).stat().st_size,'sha256':PARENT_SHA}
    rows=contract.get('locked_files',[])
    require(len(rows)==len({r['path'] for r in rows}), 'Duplicate source lock')
    locked={r['path']:r for r in rows}
    require(set(locked)==OWN_INPUTS|set(inherited_pins), 'R76 exact source lock scope changed')
    require(all(locked[n]==r for n,r in inherited_pins.items()), 'R75 inherited source locks changed')
    for n,r in locked.items():
        data=safe(root,n).read_bytes()
        require(len(data)==r['bytes'] and sha(data)==r['sha256'], 'R76 source bytes changed: '+n)
    actual={str(p.relative_to(root)) for p in (root/'r76-build-route').rglob('*')
            if p.is_file() and p.name!='foundation-contract.json' and '__pycache__' not in p.parts}
    require(actual==OWN_INPUTS, 'R76 actual upload scope changed')
    writes=contract.get('writes',[])
    require(len(writes)==3 and {r['destination'] for r in writes}=={VENDOR+s+'.c' for s in STEMS.values()},
            'Only three exact MCA postimages are approved')
    for n,s in STEMS.items():
        row=next(r for r in writes if r['destination']==VENDOR+s+'.c')
        require(row['mode']=='replace' and row['source']=='r76-build-route/payload/'+s+'.c', 'R76 source mapping changed')
        require((row['before_sha256'],row['after_sha256'])==PINS[n], 'R76 fixed source pre/postimage changed')
        parent_check.overlay_bytes(root,row)
    base=json.loads(safe(root,parent['base_contract']).read_text())
    original={r['path']:r['sha256'] for r in base['workspace_files']}
    for row in writes:
        require(original[row['destination']]==row['before_sha256'], 'R76 preimage not inherited from R61')
    parent_names={r['module_name'] for r in parent['modules']}
    modules=contract.get('modules',[])
    require(len(modules)==6 and {r['module_name'] for r in modules}==parent_names|set(STEMS), 'Exactly six collected targets required')
    require([r for r in modules if r['module_name'] in parent_names]==parent['modules'], 'Frozen R75 targets changed')
    require(len({r['target'] for r in modules})==6, 'Duplicate R76 build target')
    for n,s in STEMS.items():
        row=next(r for r in modules if r['module_name']==n)
        prefix='bazel-out/aarch64-fastbuild/bin/vendor/qcom/sm8850/canoe_perf/'+s+'/'
        require(row=={'module_name':n,'stem':s,'target':'//vendor/qcom/sm8850:canoe_perf/'+s,
                     'output':prefix+n+'.ko','symvers':prefix+'canoe_perf/'+s+'_Module.symvers',
                     'expected_sources':[VENDOR+s+'.c']}, 'Changed source disconnected from explicit target: '+n)
    require(contract.get('dependency_policy')=='build_declared_prerequisites_collect_six_explicit_KOs_and_symvers_not_runtime_closure',
            'Dependency collection claim changed')
    require(sha(safe(root,'r76-build-route/reference/mca_adsp_glink.h').read_bytes())==
            original[VENDOR+'drivers/power/supply/mca/include/mca/common/mca_adsp_glink.h'], 'Actual MCA public header changed')
    return {'schema':1,'status':'PASS','compile_only':True,'flashable':False,'modules':[r['module_name'] for r in modules],
            'own_inputs':len(OWN_INPUTS),'locked_files':len(locked),'new_writes':3,'total_overlay_writes':10,
            'inherited_R75_R61_verified':True,'runtime_abi_compatible':'NOT_YET_VALIDATED'}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,required=True)
    root=parser.parse_args().root.resolve()
    print(json.dumps(check(root,json.loads((root/'r76-build-route/foundation-contract.json').read_text())),indent=2))
