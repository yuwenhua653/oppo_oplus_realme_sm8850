#!/usr/bin/env python3
"""Execute exact production CP setup and resource lifetime bodies."""
import argparse,hashlib,json,os,re,subprocess
from pathlib import Path
from extract import extract
HERE=Path(__file__).resolve().parent
ROOTS=['sc8581_init_device','cp_charge_detect_device','sc8581_dump_important_regs','sc8581_irq_handler']
def pin(p):
 b=p.read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def functions(text):
 names=set(re.findall(r'^static\s+[^;{}]*?\b(\w+)\s*\([^;{}]*\)\s*\n\{',text,re.M))
 return {n:extract(text,n) for n in names}
def header():
 s=(HERE/'sc8581.h').read_text();return re.sub(r'^#include <linux/[^>]+>\n','',s,flags=re.M)
def core(source,out):
 text=source.read_text();fs=functions(text);fs.pop('sc8581_abnormal_charging_judge');needed=set()
 def visit(name):
  if name in needed:return
  needed.add(name);code=re.sub(r'/\*.*?\*/|//[^\n]*','',fs[name],flags=re.S)
  for called in re.findall(r'\b(\w+)\s*\(',code):
   if called in fs:visit(called)
 for n in ROOTS:visit(n)
 names=sorted(needed,key=lambda n:text.index(fs[n]));bodies=[fs[n] for n in names]
 enums='\n'.join(e for e in re.findall(r'enum\s+\w+\s*\{[^}]+\};',text,re.S) if 'CP_REG_MAX' in e)
 prototypes='\n'.join(f[:f.index('{')].strip()+';' for f in bodies)
 defines='\n'.join(line for line in text.splitlines() if re.match(r'#define\s+(SC8581_ADC_REG_BASE|MCA_SET_OVPGATE_COUNT|MANUAL_GATE_MASK|CP_DUMP_REG_LEN)\b',line))
 locks='\n'.join(re.findall(r'^static DEFINE_MUTEX\([^;]+;',text,re.M))
 generated=(HERE/'core_host.h').read_text()+'\n#include "sc8581_reg.h"\n#include "interrupt_enum.h"\n'+header()+'\nstatic void sc8581_abnormal_charging_judge(struct sc8581_device *bq,u8 *data) {(void)bq;(void)data;judges++;}\n'+defines+'\n'+locks+'\n'+enums+'\n'+prototypes+'\n'+'\n\n'.join(bodies)+'\n'+(HERE/'core_cases.c').read_text()
 return compile_c(generated,out),names
def compile_c(generated,out):
 out.mkdir(parents=True,exist_ok=False);c=out/'production.c';c.write_text(generated)
 command=['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie','-I',str(HERE),str(c),'-o',str(out/'test')]
 run=subprocess.run(command,text=True,capture_output=True);(out/'build.log').write_text(run.stdout+run.stderr);assert run.returncode==0,run.stderr
 return command
def run(exe,case=None):
 return subprocess.run([str(exe)]+([case] if case else []),capture_output=True,text=True,timeout=40,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0:abort_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'})
LIFECYCLE=['sc8581_restore_nlpm','sc8581_disable_irq_wake','sc8581_cancel_irq_work','sc8581_quiesce_device','sc8581_disable_wakeup','sc8581_init_gpio','sc8581_register_irq','sc8581_probe']
def build_lifecycle(source,out):
 text=source.read_text()
 text=re.sub(r'#if \(LINUX_VERSION_CODE >= KERNEL_VERSION\(6, 6, 9\)\)\nstatic int sc8581_probe\(struct i2c_client \*client\)\n#else\nstatic int sc8581_probe\(struct i2c_client \*client,\n\s*const struct i2c_device_id \*id\)\n#endif','static int sc8581_probe(struct i2c_client *client)',text)
 fs=functions(text);names=[n for n in LIFECYCLE if n in fs];names.sort(key=lambda n:text.index(fs[n]))
 missing=[n for n in LIFECYCLE[:5] if n not in fs]
 fallbacks='\n'.join('static void '+n+'(void *data) {(void)data;}' for n in missing)
 generated=(HERE/'lifecycle_host.h').read_text()+'\n'+fallbacks+'\n'+'\n\n'.join(fs[n] for n in names)+'\n'+(HERE/'lifecycle_cases.c').read_text()
 return compile_c(generated,out),names
def lifecycle(source,before,out,result):
 cmd,names=build_lifecycle(source,out/'lifecycle-candidate');r=run(out/'lifecycle-candidate/test');(out/'lifecycle-candidate/run.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
 build_lifecycle(before,out/'lifecycle-original');neg={}
 for case in ['gpio','provider','irq-cleanup']:
  old=run(out/'lifecycle-original/test',case);(out/'lifecycle-original'/f'{case}.log').write_text(old.stdout+old.stderr)
  assert old.returncode!=0 and 'FAIL lifecycle' in old.stderr and 'ERROR: AddressSanitizer' not in old.stderr and 'runtime error:' not in old.stderr,case+old.stderr
  neg[case]=old.stderr.splitlines()[0]
 result['lifecycle']={'functions':names,'compiler':cmd,'output':r.stdout.strip(),'original_negative_proofs':neg}
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--before',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--core-only',action='store_true');a=p.parse_args()
 a.out.mkdir(parents=True,exist_ok=False);cmd,names=core(a.source,a.out/'core-candidate');r=run(a.out/'core-candidate/test');(a.out/'core-candidate/run.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
 oldcmd,_=core(a.before,a.out/'core-original');neg={}
 for case in ['rmw','block','init','irq','concurrency']:
  original=run(a.out/'core-original/test',case);(a.out/f'core-original/{case}.log').write_text(original.stdout+original.stderr)
  assert original.returncode!=0 and 'FAIL ' in original.stderr and 'ERROR: AddressSanitizer' not in original.stderr and 'runtime error:' not in original.stderr,case
  neg[case]=original.stderr.splitlines()[0]
 current=run(a.out/'core-candidate/test','success');original=run(a.out/'core-original/test','success');assert current.returncode==original.returncode==0 and current.stdout==original.stdout,(current.stdout,original.stdout)
 result={'status':'PASS_CP_CORE_ONLY','source':pin(a.source),'before':pin(a.before),'register_header':pin(HERE/'sc8581_reg.h'),'device_header':pin(HERE/'sc8581.h'),'core_functions':names,'compiler':cmd,'output':r.stdout.strip(),'original_negative_proofs':neg,'success_register_images_identical':current.stdout,'hardware_tested':False,'limitation':'Exact extracted production helpers against synthetic SMBus, GPIO, scheduler and devres. No real CP writes or hardware acceptance asserted.'}
 if not a.core_only:
  lifecycle(a.source,a.before,a.out,result)
  result['status']='PASS_CP_PRODUCTION_C_FAULT_MATRIX'
 (a.out/'RESULT.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(r.stdout.strip());print(result['status'])
if __name__=='__main__':main()
