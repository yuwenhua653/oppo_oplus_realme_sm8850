#!/usr/bin/env python3
"""Compile actual consumer, strategy fanout and BQ setter bodies with fault injection."""
import argparse,hashlib,json,os,re,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
NAMES=['mca_quick_charge_can_tbat_do_charge','mca_quick_charge_start_charging','mca_quick_charge_monitor_work','mca_quick_charge_process_event']
def extract(text,name):
 pattern=r'^static\s+[^;{}]*?\b'+re.escape(name)+r'\s*\([^;{}]*\)\s*\n\{'
 matches=list(re.finditer(pattern,text,re.M));assert matches,name
 m=matches[-1];start=m.start();i=text.index('{',m.start());level=0;state='code'
 while i<len(text):
  c=text[i];two=text[i:i+2]
  if state=='code':
   if two=='/*':state='comment';i+=2;continue
   if two=='//':state='line';i+=2;continue
   if c in '\"\'':state=c
   elif c=='{':level+=1
   elif c=='}':
    level-=1
    if not level:return text[start:i+1]
  elif state=='comment':
   if two=='*/':state='code';i+=2;continue
  elif state=='line':
   if c=='\n':state='code'
  elif c=='\\':i+=2;continue
  elif c==state:state='code'
  i+=1
 raise ValueError(name)
def pin(path):
 b=path.read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def build(q,b,s,header,out):
 text=q.read_text();bodies={n:extract(text,n) for n in NAMES}
 enum=re.search(r'enum strategy_fg_type\s*\{.*?\};',header.read_text(),re.S).group(0)
 assert 'MCA_FG_TYPE_SINGLE_NUM_MAX = MCA_FG_TYPE_SINGLE' in enum and 'MCA_FG_TYPE_SINGLE = 0' in enum
 c=enum+'\n_Static_assert(MCA_FG_TYPE_SINGLE_NUM_MAX == 0, \"single FG enum\");\n_Static_assert(MCA_FG_TYPE_PARALLEL == 1, \"parallel FG enum\");\n'+(HERE/'host.h').read_text()+'\n'+extract(b.read_text(),'fg_set_fastcharge_mode')+'\n'+extract(s.read_text(),'strategy_fg_ops_set_fastcharge')+'\n'+(HERE/'bridge.c').read_text()+'\n'+'\n\n'.join(bodies.values())+'\n'+(HERE/'cases.c').read_text()
 out.mkdir(parents=True,exist_ok=False);source=out/'quickchg.c';source.write_text(c)
 cmd=['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie',str(source),'-o',str(out/'test')]
 r=subprocess.run(cmd,text=True,capture_output=True);(out/'build.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
 return cmd,bodies
def run(exe,case=None):
 return subprocess.run([str(exe)]+([case] if case else []),text=True,capture_output=True,timeout=30,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0:abort_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'})
def main():
 p=argparse.ArgumentParser();p.add_argument('--quickchg',type=Path,required=True);p.add_argument('--bq',type=Path,required=True);p.add_argument('--strategy',type=Path,required=True);p.add_argument('--strategy-header',type=Path,required=True);p.add_argument('--before-quickchg',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 cmd,bodies=build(a.quickchg,a.bq,a.strategy,a.strategy_header,a.out/'current');r=run(a.out/'current/test');(a.out/'current/run.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
 negative={}
 if a.before_quickchg:
  build(a.before_quickchg,a.bq,a.strategy,a.strategy_header,a.out/'original')
  expected={'start':'class_calls==1','monitor':'class_calls==1','instances':'provider_writes[0]==2','thermal':'mca_quick_charge_can_tbat_do_charge(0,&i,initial)==-EIO','disconnect':'mca_quick_charge_process_event(MCA_EVENT_USB_DISCONNECT,0,&i)==-EIO'}
  for case,assertion in expected.items():
   r0=run(a.out/'original/test',case);(a.out/'original'/f'{case}.log').write_text(r0.stdout+r0.stderr)
   assert r0.returncode!=0,case+' unexpectedly passed original'
   assert re.search(r'^FAIL line \d+: '+re.escape(assertion)+r'$',r0.stderr,re.M),case+' failed without the intended production-behavior assertion: '+r0.stderr
   assert 'ERROR: AddressSanitizer' not in r0.stderr and 'runtime error:' not in r0.stderr,case+' sanitizer fault is not a negative proof'
   negative[case]={'status':'FAILS_EXACT_ORIGINAL','assertion':assertion}
 result={'status':'PASS_ACTUAL_QUICKCHG_BQ_STRATEGY_C_FAULT_MATRIX','quickchg':pin(a.quickchg),'bq':pin(a.bq),'strategy':pin(a.strategy),'strategy_header':pin(a.strategy_header),'single_fg_enum':0,'parallel_fg_enum':1,'functions':{n:hashlib.sha256(v.encode()).hexdigest() for n,v in bodies.items()},'compiler':cmd,'output':r.stdout.strip(),'original_negative_proofs':negative,'hardware_tested':False,'limit':'Extracted production callers and cache run against stubbed transport, charge-path dependencies and scheduler; no real hardware or complete kernel lifetime proof.'}
 (a.out/'RESULT.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(r.stdout.strip())
if __name__=='__main__':main()
