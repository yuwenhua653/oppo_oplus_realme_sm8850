#!/usr/bin/env python3
"""Independent extraction and C execution of merged production helpers."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
def pin(b):return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
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
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 text=a.source.read_text();names=['__fg_read_block','__fg_write_block','fg_write_block','fg_read_block','checksum','fg_write_read_block','fg_mac_read_frame_locked','fg_mac_read_block_variable','fg_mac_read_block','fg_mac_write_block_locked','fg_mac_write_block','fg_set_fastcharge_mode','StringToHex','fg_sha256_auth','get_verify_digest','set_verify_digest','fg_set_force_report_full']
 bodies={n:extract(text,n) for n in names};a.out.mkdir(parents=True,exist_ok=False)
 generated=(HERE/'host.h').read_text()+'\n'+'\n\n'.join(bodies.values())+'\n'+(HERE/'cases.c').read_text();c=a.out/'peer.c';c.write_text(generated)
 command=['cc','-std=gnu11','-O1','-g','-pthread','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-but-set-variable','-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie',str(c),'-o',str(a.out/'peer')]
 build=subprocess.run(command,text=True,capture_output=True);(a.out/'build.log').write_text(build.stdout+build.stderr);assert build.returncode==0,build.stderr
 import os
 run=subprocess.run([str(a.out/'peer')],capture_output=True,text=True,timeout=40,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0:abort_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'})
 (a.out/'run.log').write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr
 result={'status':'PASS_INDEPENDENT_PRODUCTION_C_MAC_AUTH_MATRIX','source':pin(a.source.read_bytes()),'functions':{k:pin(v.encode()) for k,v in bodies.items()},'compiler':command,'output':run.stdout,'ASan_UBSan_Werror':True,'leak_detection':False,'limitation':'Kernel hardware/target CI compilation and full charging policy activation are not asserted.'}
 (a.out/'RESULT.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(run.stdout.strip())
if __name__=='__main__':main()
