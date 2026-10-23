#!/usr/bin/env python3
"""Compare actual R88/R89 probe and battery parsing with fault-injected providers."""
import argparse, hashlib, json, os, subprocess
from pathlib import Path
from extract import function
HERE=Path(__file__).resolve().parent
NAMES=['mca_quick_charge_parse_temp_para','mca_quick_charge_check_model_name','mca_quick_charge_parse_batt_info','mca_quick_charge_probe']
PREIMAGE='53602b92b5c362b9658bc751fc7554b6c83d3bebd5b2fee1754f24ae0987d355'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--before',required=True,type=Path);p.add_argument('--source',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
 assert sha(a.before.read_bytes())==PREIMAGE,'Exact R88 quickchg preimage required'
 a.out.mkdir(parents=True,exist_ok=False)
 results={};traces={}
 for label,path in [('before',a.before),('candidate',a.source)]:
  s=path.read_text();bodies={n:function(s,n) for n in NAMES}
  diag=''
  if label=='candidate':
   start=s.index('/* R89: a read-only snapshot');end=s.index('MODULE_PARM_DESC(probe_status',start);end=s.index('\n',end)+1
   diag='#define DIAG_ENABLED 1\n'+s[start:end]
  generated=(HERE/'host.h').read_text()+'\n'+diag+'\n'+'\n'.join(bodies.values())+'\n'+(HERE/'cases.c').read_text()
  c=a.out/(label+'.c');c.write_text(generated);exe=a.out/label
  cmd=['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-but-set-variable','-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie','-pthread',str(c),'-o',str(exe)]
  r=subprocess.run(cmd,capture_output=True,text=True);(a.out/(label+'-build.log')).write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
  r=subprocess.run([str(exe.resolve())],capture_output=True,text=True,timeout=30,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0:abort_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'})
  (a.out/(label+'-trace.log')).write_text(r.stdout);(a.out/(label+'-run.log')).write_text(r.stderr);assert r.returncode==0,r.stdout+r.stderr
  results[label]={'source_sha256':sha(path.read_bytes()),'functions':{n:sha(b.encode()) for n,b in bodies.items()},'compiler':cmd,'result':r.stderr.strip()};traces[label]=r.stdout
 assert traces['before']==traces['candidate'],'Production dependency operation trace or return changed'
 report={'status':'PASS','scenario_count':24,'trace_sha256':sha(traces['candidate'].encode()),'production_functions':NAMES,'results':results,'target_compiled':False,'hardware_tested':False,'scope':'Actual probe, battery selector, model-name mapping and temperature parser. Kernel/provider/allocation/registration interfaces and synthetic DT table fixtures are stubbed. Unchanged operations and returns are compared with exact R88. Numeric fixture constants describe test topology, not target ABI.'}
 (a.out/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n');print('PASS 24 production scenarios; identical R88/R89 operation traces and returns; diagnostics, retry reset, and concurrent attempt ownership validated')
if __name__=='__main__':main()
