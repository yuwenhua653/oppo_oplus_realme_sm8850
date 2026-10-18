#!/usr/bin/env python3
"""Test source-extracted production transport functions with real host threads."""
import argparse,hashlib,json,os,pathlib,re,shutil,subprocess
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parent
ap=argparse.ArgumentParser();ap.add_argument('--source',type=pathlib.Path,default=ROOT/'candidate/drivers/soc/qcom/qti_pmic_glink.c');ap.add_argument('--header',type=pathlib.Path,default=ROOT/'candidate/include/linux/soc/qcom/qti_pmic_glink.h');ap.add_argument('--output',type=pathlib.Path,default=ROOT/'test-output');a=ap.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
s=a.source.read_text();parts={}
def function(name):
 # Definition starts at the previous blank line and ends at a balanced top-level brace.
 m=re.search(r'^'+re.escape(name)+r'\s*\(',s,re.M) or re.search(r'^\w[^;{}\n]*\b'+re.escape(name)+r'\s*\(',s,re.M)
 if not m:raise ValueError('missing definition '+name)
 start=s.rfind('\n\n',0,m.start())+2;brace=s.index('{',m.start());i=brace;depth=0;quote=None;comment=None
 while i<len(s):
  c=s[i];n=s[i:i+2]
  if comment=='line':
   if c=='\n':comment=None
  elif comment=='block':
   if n=='*/':comment=None;i+=1
  elif quote:
   if c=='\\':i+=1
   elif c==quote:quote=None
  elif n=='//':comment='line';i+=1
  elif n=='/*':comment='block';i+=1
  elif c in ('"',"'"):quote=c
  elif c=='{':depth+=1
  elif c=='}':
   depth-=1
   if not depth:return s[start:i+1]+'\n'
  i+=1
 raise ValueError('unbalanced '+name)
parts['types_globals_callback_helpers_and_notify']=s[s.index('struct pmic_glink_dev {'):s.index('static int pmic_glink_ssr_notifier_cb(')]
for name in ['get_pmic_glink_from_dev','pmic_glink_write','pmic_glink_register_client','pmic_glink_unregister_client','pmic_glink_unregister_client_sync','pmic_glink_rx_callback']:parts[name]=function(name)
(out/'production_functions.c').write_text('#define GLINK_READ_FAIL_RETRIES 5\n'+'\n'.join(parts.values()))
(out/'api_under_test.h').write_bytes(a.header.read_bytes());stubs=out/'stubs/linux';stubs.mkdir(parents=True,exist_ok=True);(stubs/'types.h').write_text('#include "fake_kernel.h"\n')
cc=shutil.which('gcc');assert cc
flags=['-std=gnu11','-O1','-g','-pthread','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-fsanitize=address,undefined','-fno-omit-frame-pointer']
cmd=[cc,*flags,'-I'+str(HERE),'-I'+str(out),'-I'+str(out/'stubs'),str(HERE/'test_transport.c'),'-o',str(out/'test_transport')]
c=subprocess.run(cmd,text=True,capture_output=True);(out/'compile.log').write_text(c.stdout+c.stderr)
if c.returncode:print(c.stdout+c.stderr);raise SystemExit(c.returncode)
env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:abort_on_error=1',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
r=subprocess.run([str(out/'test_transport')],text=True,capture_output=True,env=env,timeout=30);(out/'run.log').write_text(r.stdout+r.stderr)
report={'status':'PASS' if r.returncode==0 else 'FAIL','source_sha256':hashlib.sha256(a.source.read_bytes()).hexdigest(),'header_sha256':hashlib.sha256(a.header.read_bytes()).hexdigest(),'production_extraction':[{'name':n,'bytes':len(v.encode()),'sha256':hashlib.sha256(v.encode()).hexdigest()} for n,v in parts.items()],'compiler':subprocess.check_output([cc,'--version'],text=True).splitlines()[0],'flags':flags,'returncode':r.returncode,'stdout':r.stdout,'limits':['Real production functions/types are source-extracted, not a rewritten model. Kernel synchronization, allocation and IDR use host shims; RPMSG send is mocked.','PMIC parent remains bound; parent hot-remove and invalid-handle callers are outside this patch and these tests.','Host fixtures are not a target kernel build or device qualification.']};(out/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));raise SystemExit(r.returncode)
