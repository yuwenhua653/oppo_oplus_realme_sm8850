#!/usr/bin/env python3
"""Compile exact CP telemetry/retry production functions with fault injection."""
import argparse,hashlib,json,os,subprocess
from pathlib import Path
from extract import function,span
HERE=Path(__file__).resolve().parent
NAMES=['mca_qc_quick_charge_update_ibus','mca_quick_charge_tune_vbus','mca_get_qc_vbus_tune_status','mca_qc_retry_to_enable_cp']
OLD_SHA='4ffacd13662ab262fcc41ab49468e8f88539f36552e6f43136a3490feb942e25'
NEGATIVES=['adc_error','current_error','vbus_error','tune_request_error','retry_enable_error','retry_current_error','retry_request_error','qc_errorhl_error']
def pin(data):return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
def build(source,out):
 text=source.read_text();bodies={name:function(text,name) for name in NAMES}
 caller=function(text,'mca_qc_quick_charge_open_path');start=caller.index('\tfor (i = 0; i < MCA_QC_QUICK_CHG_OPEN_PATH_COUNT; i++)');opening=caller.index('{',start)
 prefix='static void extracted_loop(void)\n';wrapped=prefix+caller[opening:];_,end=span(wrapped,'extracted_loop');loop=caller[start:opening]+wrapped[len(prefix):end]
 wrapper='static int actual_qc_open_loop(struct mca_quick_charge_info *info,int *final_status) { int ret=0,i;enum VBUS_TUNE_STAT status;\n'+loop+'\n*final_status=status;return ret;}\n'
 generated=(HERE/'host.h').read_text()+'\n'+'\n\n'.join(bodies.values())+'\n'+wrapper+(HERE/'cases.c').read_text()
 out.mkdir(parents=True,exist_ok=False);c=out/'production.c';c.write_text(generated)
 cmd=['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie',str(c),'-o',str(out/'tests')]
 p=subprocess.run(cmd,capture_output=True,text=True);(out/'build.log').write_text(p.stdout+p.stderr);assert p.returncode==0,p.stderr
 return {'source':pin(source.read_bytes()),'functions':{k:pin(v.encode()) for k,v in bodies.items()},'unmodified_actual_QC_open_loop':pin(loop.encode()),'compiler':cmd}
def run(exe,*args):
 return subprocess.run([str(exe),*args],capture_output=True,text=True,timeout=30,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0:abort_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'})
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',required=True,type=Path);p.add_argument('--before',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
 assert pin(a.before.read_bytes())['sha256']==OLD_SHA,'Exact compiled R86 source required'
 after=build(a.source,a.out/'candidate');r=run(a.out/'candidate/tests');(a.out/'candidate/run.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
 before=build(a.before,a.out/'original');proofs={}
 for case in NEGATIVES:
  old=run(a.out/'original/tests',case);(a.out/'original'/f'{case}.log').write_text(old.stdout+old.stderr)
  assert old.returncode==41 and f'FAIL {case}: result == error' in old.stderr,case+' wrong failure: '+old.stderr
  assert 'ERROR: AddressSanitizer' not in old.stderr and 'runtime error:' not in old.stderr
  proofs[case]=old.stderr.strip()
 old=run(a.out/'original/tests','success');new=run(a.out/'candidate/tests','success');assert old.returncode==new.returncode==0 and old.stdout==new.stdout,'Success-path trace changed'
 (a.out/'success-traces.log').write_text(new.stdout)
 report={'schema':1,'status':'PASS_ACTUAL_QUICKCHG_CP_ERROR_CHAIN','candidate':after,'before':before,'original_negative_proofs':proofs,'output':r.stdout.splitlines()[-1],'success_path_scenarios':len(new.stdout.splitlines()),'success_trace_sha256':hashlib.sha256(new.stdout.encode()).hexdigest(),'ASan_UBSan_Werror':True,'target_compiled':False,'hardware_tested':False,'limitation':'Production four-function error chain and exact unchanged QC-open loop, with stubbed CP ADC/current/voltage/enable, protocol and scheduler. The full caller outside that loop, real voltage commands and kernel lifetime are not executed.'}
 (a.out/'RESULT.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(report['output']);print('PASS eight exact R86 negative proofs and identical success-path operation traces')
if __name__=='__main__':main()
