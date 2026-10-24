#!/usr/bin/env python3
"""Run exact production parsers with pinned stock DT properties and faulted OF/alloc APIs."""
import argparse,hashlib,json,os,re,subprocess,zipfile
from pathlib import Path
from extract import function
HERE=Path(__file__).resolve().parent
PREIMAGE='55627d74ab0ffb074548aca1cac3fedecc2b6268a89ffb93fb0e1e5f187c350f'
NAMES=['mca_quick_charge_parse_volt_para','mca_quick_charge_parse_stage_para','mca_quick_charge_parse_temp_para','mca_quick_charge_jump_stage']
def sha(b):return hashlib.sha256(b).hexdigest()
def production_types(header):
 parts=[]
 for name in ['TEMP_PARA_MAX_GROUP','VOLT_PARA_MAX_GROUP']:
  parts.append(re.search(r'^#define '+name+r' .+$',header,re.M).group())
 for kind,name in [('enum','mca_quick_charge_temp_para_ele'),('enum','mca_quick_charge_volt_para_ele'),('struct','mca_quick_charge_temp_para'),('struct','mca_quick_charge_volt_para'),('struct','mca_quick_charge_volt_para_info'),('struct','mca_quick_charge_temp_para_info'),('struct','mca_quick_charge_batt_para_info')]:
  parts.append(re.search(r'^'+kind+' '+name+r' \{.*?^\};',header,re.M|re.S).group())
 return '\n'.join(parts)
def helpers(source):
 parts=[]
 for name in ['mca_parse_dts_count_strings','mca_parse_dts_string_index','mca_parse_dts_u32_array']:
  begin=source.index('int '+name+'(');end=source.index('\nEXPORT_SYMBOL',begin)
  parts.append(source[begin:end])
 return '\n'.join(parts)
def fixtures(data):
 code=[]
 for label,nodepath in [('cn','/soc/mca_strategy_quick_charge'),('gbl','/soc/mca_quick_charge_batt_para_gbl')]:
  props=data['nodes'][nodepath]['properties'];needed=set()
  for name in ['batt_para_atl','batt_para_cos']:
   if name in props:
    needed.add(name);raw=props[name]
    for i in range(0,len(raw),9):needed.update(x for x in raw[i+5:i+9] if x!='null')
  rows=[]
  for i,name in enumerate(sorted(needed)):
   values=props[name];var=f'{label}_p{i}';strings=all(isinstance(x,str) for x in values)
   code.append(('static const char *' if strings else 'static const u32 ')+var+'[] = {'+','.join(json.dumps(x) for x in values)+'};')
   rows.append('{'+json.dumps(name)+(','+var+','+str(len(values))+',NULL,0}' if strings else ',NULL,0,'+var+','+str(len(values))+'}'))
  code.append('static struct property '+label+'_properties[] = {'+','.join(rows)+'};')
  code.append('static struct device_node fixture_'+label+' = {'+label+'_properties,'+str(len(rows))+'};')
 return '\n'.join(code)
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--before',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 assert sha(a.before.read_bytes())==PREIMAGE,'Exact R89 required'
 prov=json.loads((HERE/'PROVENANCE.json').read_bytes());raw=(HERE/'stock-charging-nodes.json').read_bytes();assert sha(raw)==prov['stock_dt']['sha256']
 for name in ['mca_parse_dts.c','mca_quick_charger.h']:
  assert sha((HERE/name).read_bytes())==prov['pinned_inputs'][name]['sha256']
 a.out.mkdir(parents=True,exist_ok=False);header=(HERE/'host.h').read_text().replace('/* PRODUCTION_TYPES */',production_types((HERE/'mca_quick_charger.h').read_text()))
 common=header+'\n'+helpers((HERE/'mca_parse_dts.c').read_text())+'\n'+fixtures(json.loads(raw))
 results={}
 for label,path in [('before',a.before),('candidate',a.source)]:
  source=path.read_text();bodies={n:function(source,n) for n in NAMES}
  generated='#define CANDIDATE '+str(int(label=='candidate'))+'\n'+common+'\n'+'\n'.join(bodies.values())+'\n'+(HERE/'cases.c').read_text()
  c=a.out/(label+'.c');c.write_text(generated);exe=a.out/label
  cmd=['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-misleading-indentation','-Wno-pointer-sign','-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie',str(c),'-o',str(exe)]
  r=subprocess.run(cmd,capture_output=True,text=True);(a.out/(label+'-build.log')).write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
  r=subprocess.run([str(exe.resolve())],capture_output=True,text=True,timeout=90,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0:abort_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'})
  (a.out/(label+'-run.log')).write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
  results[label]={'source_sha256':sha(path.read_bytes()),'functions':{n:sha(s.encode()) for n,s in bodies.items()},'result':r.stdout.strip()}
 record={'schema':1,'status':'PASS_R90_ACTUAL_PRODUCTION_PARSERS','results':results,'fixture_provenance':prov,'source_scope':'Production temp/volt/stage/jump functions and production mca DT count/string/u32 wrappers. Kernel OF, allocation and diagnostics are host substitutes. Three stock nine-column tables and their original referenced voltage/stage properties; constructed eleven-column equivalents and fault/edge cases.','hardware_tested':False,'target_compiled':False}
 (a.out/'RESULT.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
if __name__=='__main__':main()
