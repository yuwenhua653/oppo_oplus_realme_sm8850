#!/usr/bin/env python3
"""Validate exact final R90 production parser sources and retained charging error behavior."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
PREFIX='vendor/qcom/sm8850/drivers/power/supply/mca/'
QUICK=PREFIX+'mca_strategy/strategy_charger/mca_strategy_quickchg.c'
BQ=PREFIX+'mca_hardware_ic/fuelgauge_ic/bq27z561/bq27z561.c'
def pin(path):
 b=Path(path).read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def main():
 p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 route=Path(__file__).resolve().parent;repo=route.parent;root=a.workspace.resolve();out=a.output.resolve()
 sys.path.insert(0,str(route/'tests/temp_schema'));from extract import span
 source=root/QUICK;before=route/'preimage/mca_strategy_quickchg.c'
 # Successful policy, table selector, source header and unrelated functions stay exact.
 texts=[]
 for path in [before,source]:
  text=path.read_text();ranges=[span(text,n) for n in ['mca_quick_charge_parse_volt_para','mca_quick_charge_parse_stage_para','mca_quick_charge_parse_temp_para']]
  for start,end in sorted(ranges,reverse=True):text=text[:start]+text[end:]
  texts.append(text)
 assert texts[0]==texts[1],'Only three local parsing functions may change'
 for fixture,destination in [('mca_quick_charger.h',PREFIX+'mca_strategy/strategy_charger/inc/mca_quick_charger.h'),('mca_parse_dts.c',PREFIX+'mca_common/mca_parse_dts.c')]:
  assert pin(route/'tests/temp_schema'/fixture)==pin(root/destination),'Actual production header/helper differs from pinned host extraction'
 contract=json.loads((route/'SOURCE-CONTRACT.json').read_bytes());assert len(contract['writes'])==1 and contract['writes'][0]['path']==QUICK
 assert pin(source)==contract['writes'][0]['after'],'Final source contract mismatch'
 assert pin(before)==contract['writes'][0]['before'],'Negative-control source mismatch'
 assert not out.exists() and not out.is_symlink(),'Fresh output required';out.mkdir(parents=True)
 jobs=[('temperature_schema',route/'tests/temp_schema/run_tests.py',['--before',str(before),'--source',str(source)]),('retained_fastcharge_fanout',repo/'r87-build-route/tests/fanout/run_tests.py',['--quickchg',str(source),'--bq',str(root/BQ),'--strategy',str(root/(PREFIX+'mca_strategy/strategy_fg/mca_strategy_fg.c')),'--strategy-header',str(root/(PREFIX+'mca_strategy/strategy_fg/inc/strategy_fg.h'))])]
 reports=[]
 for name,script,args in jobs:
  result=subprocess.run([sys.executable,'-B',str(script),*args,'--out',str(out/name)],capture_output=True,text=True,timeout=180)
  (out/(name+'.log')).write_text(result.stdout+result.stderr);assert result.returncode==0,name+' failed: '+result.stdout+result.stderr
  reports.append({'name':name,'script':str(script.relative_to(repo)),'script_pin':pin(script),'returncode':result.returncode})
 record={'schema':1,'status':'PASS_R90_PRODUCTION_SOURCE_TESTS','tests':reports,'sources':{QUICK:pin(source)},'unchanged_outside_three_parse_functions':True,'target_compile_tested':False,'hardware_tested':False,'limit':'Actual extracted C on host with pinned stock table fixtures and synthetic dependency fault injection; CI performs complete 47-module compilation.'}
 (out/'RESULT.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
if __name__=='__main__':main()
