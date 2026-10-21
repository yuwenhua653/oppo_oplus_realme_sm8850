#!/usr/bin/env python3
import argparse,hashlib,json,re,subprocess,os
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
ORIGINAL=ROOT/'recovery/myron-r83-validation-output/source/r83-build-route/validation-reference/vendor/qcom/sm8850/drivers/iio/adc/qcom-spmi-adc5-gen3.c'
NAMES=['adc5_gen3_state_error','adc5_gen3_update_dig_param','adc5_gen3_configure','adc5_gen3_read_voltage_data','adc5_gen3_do_conversion','get_sdam_from_irq','adc5_gen3_clear_conv_fault','adc5_gen3_isr','tm_err_handler_work','tm_handler_work','adc5_gen3_read_raw','adc_tm_gen3_get_temp','adc_tm5_gen3_configure','adc_tm5_gen3_set_trip_temp','notify_adc_tm_fn','adc_tm_register_tzd','adc5_gen3_free_irqs','adc5_gen3_request_irqs','adc5_gen3_publish_ready','adc5_gen3_quiesce','adc5_gen3_destroy_queues','adc5_gen3_disable_channels','adc5_gen3_unpublish','adc5_gen3_cleanup','adc5_gen3_probe','adc5_gen3_exit','adc5_gen3_freeze','adc5_gen3_restore','adc5_gen3_suspend','adc5_gen3_resume']

def close(s,start):
    depth=0;state='normal';i=start
    while i<len(s):
        c=s[i];n=s[i:i+2]
        if state=='line':
            if c=='\n':state='normal'
        elif state=='block':
            if n=='*/':state='normal';i+=1
        elif state in ('"',"'"):
            if c=='\\':i+=1
            elif c==state:state='normal'
        elif n=='//':state='line';i+=1
        elif n=='/*':state='block';i+=1
        elif c in ('"',"'"):state=c
        elif c=='{':depth+=1
        elif c=='}':
            depth-=1
            if not depth:return i+1
        i+=1
    raise ValueError('unclosed source block')

def function(s,name):
    matches=list(re.finditer(r'^(?:static\s+)?(?:[\w*]+\s+)+\*?'+re.escape(name)+r'\s*\(',s,re.M))
    for m in matches:
        brace=s.find('{',m.start());semi=s.find(';',m.start())
        if semi>=0 and semi<brace:continue
        return m.start(),s[m.start():close(s,brace)]
    return None

def typeblock(s,kind,name):
    m=re.search(r'^'+kind+r'\s+'+name+r'\s*\{',s,re.M)
    if not m:return ''
    b=s.find('{',m.start());return s[m.start():close(s,b)+1]

def generate(source,original=False):
    s=source.read_text();parts=['#include "fake_kernel.h"']
    lines=s.splitlines(True); macros=[];i=0
    while i<len(lines):
        if lines[i].startswith('#define '):
            line=lines[i];b=line;i+=1
            while line.rstrip('\r\n').endswith('\\') and i<len(lines):
                line=lines[i];b+=line;i+=1
            macros.append(b)
        else:i+=1
    parts+=macros
    for name in ['adc5_cal_method','adc_time_select','adc_tm_type','adc5_gen3_state']:
        parts.append(typeblock(s,'enum',name))
    for name in ['adc5_base_data','adc5_channel_prop','adc5_chip']:
        parts.append(typeblock(s,'struct',name))
    parts.append('static LIST_HEAD(adc_tm_device_list);\nstatic DEFINE_MUTEX(adc_tm_device_list_lock);')
    funcs=[x for n in NAMES if (x:=function(s,n))]
    funcs.sort()
    parts.append('\n'.join(f[:f.find('{')].strip()+';' for _,f in funcs))
    parts.append('#include "fixture_support.inc"')
    for name in ['adc_tm_ops','adc_tm_ops_iio']:
        m=re.search(r'^static struct thermal_zone_device_ops '+name+r'\s*=',s,re.M);b=s.find('{',m.start());parts.append(s[m.start():close(s,b)+1])
    parts.extend(f for _,f in funcs)
    parts.append('#include "fixture_tests.inc"')
    return '\n\n'.join(parts)+'\n',[n for n in NAMES if function(s,n)]

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=ROOT/'r84-adc-fix/candidate/qcom-spmi-adc5-gen3.c');p.add_argument('--output',type=Path,default=HERE/'output');p.add_argument('--original',action='store_true');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True); text,names=generate(a.source,a.original);c=a.output/'actual-lifecycle.c';c.write_text(text);exe=a.output/'actual-lifecycle'
    cmd=['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-unused-parameter','-Wno-sign-compare','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie','-I'+str(HERE),str(c),'-o',str(exe)]
    if a.original:cmd.insert(1,'-DORIGINAL=1')
    cp=subprocess.run(cmd,text=True,capture_output=True);(a.output/'compile.log').write_text(cp.stdout+cp.stderr)
    if cp.returncode:print(cp.stderr);return cp.returncode
    env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0:abort_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
    r=subprocess.run([str(exe)],capture_output=True,text=True,env=env,timeout=30);(a.output/'run.log').write_text(r.stdout+r.stderr)
    d={'source':str(a.source),'source_sha256':hashlib.sha256(a.source.read_bytes()).hexdigest(),'extracted_whole_functions':names,'fixture_files':{p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [HERE/'fake_kernel.h',HERE/'fixture_support.inc',HERE/'fixture_tests.inc',HERE/'run_lifecycle.py']},'compiler_command':cmd,'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'original_negative_test':a.original,'scope':'Complete production function bodies. DT parsing/scaling/IRQ/devres/hardware mocked; real pthread mutex/condition coordination for selected worker/conversion/stop edges. No target kernel or hardware execution. LeakSanitizer disabled for fixture kernel primitives.'}
    (a.output/'RESULT.json').write_text(json.dumps(d,indent=2)+'\n');print(r.stdout+r.stderr)
    return 0 if (r.returncode!=0 and 'work queued before INIT_WORK' in r.stderr if a.original else r.returncode==0 and 'PASS 26 production-C lifecycle scenarios' in r.stdout) else 1
if __name__=='__main__':raise SystemExit(main())
