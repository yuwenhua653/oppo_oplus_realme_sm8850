#!/usr/bin/env python3
"""Execute the exact production mode helpers and fast-charge sysfs case."""
import argparse,hashlib,json,os,re,subprocess
from pathlib import Path
from extract import function
HERE=Path(__file__).resolve().parent

def pin(data):return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
def build(source,out):
 text=source.read_text();getter=function(text,'fg_get_fastcharge_mode');setter=function(text,'fg_set_fastcharge_mode');sysfs=function(text,'fg_sysfs_show');case=re.search(r'\tcase FG_IC_PROP_FAST_CHARGE:\n.*?\t\tbreak;',sysfs,re.S).group(0)
 generated=(HERE/'host.h').read_text()+'\n'+getter+'\n'+setter+'\nstatic ssize_t fast_mode_sysfs(struct bq_fg_chip *info,char *buf) { int val=0;ssize_t count=0;(void)val;switch(FG_IC_PROP_FAST_CHARGE) {\n'+case+'\n}return count;}\n'+(HERE/'cases.c').read_text()
 out.mkdir(parents=True,exist_ok=False);(out/'production-mode.c').write_text(generated)
 command=['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie',str(out/'production-mode.c'),'-o',str(out/'production-mode')]
 run=subprocess.run(command,capture_output=True,text=True);(out/'build.log').write_text(run.stdout+run.stderr);assert run.returncode==0,run.stderr
 return {'source':pin(source.read_bytes()),'getter':pin(getter.encode()),'setter':pin(setter.encode()),'sysfs_case':pin(case.encode()),'compiler':command}
def run(exe,args):
 return subprocess.run([str(exe),*args],capture_output=True,text=True,timeout=15,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0:abort_on_error=1','UBSAN_OPTIONS':'halt_on_error=1'})
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,default=HERE.parent/'candidate/bq27z561.c');parser.add_argument('--before',type=Path,default=HERE.parents[2]/'r85-assembly/combined/candidate/bq27z561.c');parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
 args.out.mkdir(parents=True,exist_ok=False);after=build(args.source,args.out/'candidate');result=run(args.out/'candidate/production-mode',[]);(args.out/'candidate/run.log').write_text(result.stdout+result.stderr);assert result.returncode==0,result.stdout+result.stderr
 before=build(args.before,args.out/'original');negative={}
 for name in ['cold-disable','unknown-getter','unknown-sysfs']:
  result2=run(args.out/'original/production-mode',[name]);(args.out/('original/'+name+'.log')).write_text(result2.stdout+result2.stderr);assert result2.returncode!=0 and 'FAIL ' in result2.stderr,name;negative[name]={'old_failed':True,'diagnostic':result2.stderr.splitlines()[0]}
 report={'status':'PASS_BQ_CACHE_VALID_REAL_C','candidate':after,'original':before,'original_negative_proofs':negative,'output':result.stdout.strip(),'ASan_UBSan_Werror':True,'target_compiled':False,'hardware_tested':False,'limitation':'MAC core is an injected dependency boundary; no hardware-mode readback or real gauge command is asserted.'};(args.out/'RESULT.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(result.stdout.strip());print('PASS three exact R85 negative proofs')
if __name__=='__main__':main()
