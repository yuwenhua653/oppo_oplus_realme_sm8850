#!/usr/bin/env python3
"""Exercise the production R97/legacy identity selector and unchanged R96 suite."""
import argparse, json, os, subprocess, tempfile
from pathlib import Path
from generate_native import generate
from read_candidate import need, read_image, verify_candidate

C_TEST = r'''
#define R36_UNIT_TEST
#include "r36_init.c"
#include <assert.h>
static uint64_t rc_size;
static int pin_calls,fail_at,rc_type;
static int fixture_stat(const char *p,struct stat *s){
 assert(!strcmp(p,"/system/etc/init/hw/init.rc"));
 memset(s,0,sizeof(*s));s->st_mode=rc_type?S_IFLNK|0777:S_IFREG|0644;s->st_size=rc_size;return 0;
}
static int fixture_pin(const char*p,uint64_t bytes,const char*hash,int elf){
 assert(elf);pin_calls++;
 if(!strcmp(p,"/system/bin/recovery")){
  assert(bytes==(r97_recovery_selected?R97_RECOVERY_BYTES:4063256));
  assert(!strcmp(hash,r97_recovery_selected?R97_RECOVERY_SHA256:"b0d438147ce216b24fe142c4ca3545481051144e00df00a5b2a1538676d7b472"));
 }else{
  assert(!strcmp(p,"/system/bin/init")&&r97_recovery_selected);
  assert(bytes==R97_INIT_BYTES&&!strcmp(hash,R97_INIT_SHA256));
 }
 if(pin_calls==fail_at){errno=EINVAL;return -1;}return 0;
}
static void reset(void){pin_calls=fail_at=rc_type=0;rc_size=R97_RC_BYTES;}
int main(void){
 pin_path=fixture_pin;call.lstat_fn=fixture_stat;
 assert(R36_INIT_BYTES==3356672&&!strcmp(R36_INIT_SHA256,"aa0e560d2bc15ed23a2c39af332120bd31e0355da16a20711859f9fd69234334"));
 assert(!strcmp(R36_BUILD_ID,"R94-MCA-TORCH-COMPAT-20261028-01"));
 reset();assert(!verify_recovery_bundle(R97_RECOVERY_BYTES));assert(pin_calls==2&&r97_recovery_selected);
 assert(recovery_rc_bytes==R97_RC_BYTES&&!strcmp(recovery_rc_hash,R97_RC_SHA256));
 reset();fail_at=1;assert(verify_recovery_bundle(R97_RECOVERY_BYTES));assert(pin_calls==1);
 reset();fail_at=2;assert(verify_recovery_bundle(R97_RECOVERY_BYTES));assert(pin_calls==2);
 reset();rc_size=R97_RC_BYTES+1;assert(verify_recovery_bundle(R97_RECOVERY_BYTES));
 if(R97_RC_BYTES!=5341){reset();rc_size=5341;assert(verify_recovery_bundle(R97_RECOVERY_BYTES));}
 if(R97_RC_BYTES!=10292){reset();rc_size=10292;assert(verify_recovery_bundle(R97_RECOVERY_BYTES));}
 reset();rc_type=1;assert(verify_recovery_bundle(R97_RECOVERY_BYTES));
 reset();assert(verify_recovery_bundle(0));assert(pin_calls==0&&!r97_recovery_selected);
 reset();assert(verify_recovery_bundle(UINT64_MAX));assert(pin_calls==0);
 reset();rc_size=5341;assert(!verify_recovery_bundle(4063256));assert(pin_calls==1&&!r97_recovery_selected&&recovery_rc_bytes==5341);
 reset();rc_size=10292;assert(!verify_recovery_bundle(4063256));assert(pin_calls==1&&!r97_recovery_selected&&recovery_rc_bytes==10292);
 reset();rc_size=5342;assert(verify_recovery_bundle(4063256));
 puts("PASS R97 exact bundle, failed binary/init pins, RC cross-pairing and legacy rollback; generic init/runtime unchanged");return 0;
}
'''

def test(baseline):
    with tempfile.TemporaryDirectory(prefix='r97-native-test-') as d:
        native=Path(d)/'native'
        # Only host test fixtures; CLI generation always requires a verified image.
        fake={'pins':{n:{'bytes':b,'sha256':str(i)*64} for n,b,i in [
            ('system/bin/init',4000000,1),('system/bin/recovery',5000000,2),('system/etc/init/hw/init.rc',16000,3)]},
            'test_fixture_only':True}
        generate(baseline,native,fake)
        (native/'test_r97_bundle.c').write_text(C_TEST)
        flags=['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function',
               '-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie']
        env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0:abort_on_error=1','UBSAN_OPTIONS':'halt_on_error=1'}
        results=[]
        for source in [native/'test_r97_bundle.c',native/'test_rc_selection.c',native/'tests/test_native.c']:
            exe=source.with_suffix('')
            subprocess.run(flags+[str(source),'-o',str(exe)],check=True)
            result=subprocess.run([str(exe)],env=env,check=True,capture_output=True,text=True)
            results.append({'test':source.name,'output':result.stdout+result.stderr})
        return results

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline-native',required=True)
    a=p.parse_args();print(json.dumps(test(a.baseline_native),indent=2))
