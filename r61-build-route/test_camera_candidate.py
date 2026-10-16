#!/usr/bin/env python3
"""Compile and exercise the candidate's actual copied helper and switch arms."""
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
src = (ROOT / 'payload/qcom/opensource/camera-kernel/drivers/cam_req_mgr/cam_req_mgr_dev.c').read_text()
helper = src[src.index('struct cam_req_mgr_xiaomi_session_info {'):src.index('static long cam_private_ioctl(')]
ioctl = src[src.index('static long cam_private_ioctl('):]
ioctl = ioctl[:ioctl.index('\n\tcase CAM_REQ_MGR_LINK: {')]
ioctl += '\n\tdefault: return -EINVAL;\n\t}\n\treturn rc;\n}\n'
prelude = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <assert.h>
#include <media/cam_req_mgr.h>
struct file;
static int input_fail, output_fail, backend_rc, cleanup_rc;
static unsigned creates, destroys, errors, infos;
static size_t copyin_n, copyout_n;
static struct cam_req_mgr_session_info last_create, last_destroy;
#define u64_to_user_ptr(x) ((void *)(uintptr_t)(x))
#define CAM_CRM 0
#define CAM_ERR(...) do { errors++; } while (0)
#define CAM_INFO(...) do { infos++; } while (0)
static size_t copy_from_user(void *dst, const void *src, size_t n) {
  copyin_n=n;
  if (input_fail) { memcpy(dst,src,n/2); return n-n/2; }
  memcpy(dst,src,n); return 0;
}
static size_t copy_to_user(void *dst, const void *src, size_t n) {
  copyout_n=n;
  if (output_fail) { memcpy(dst,src,n/2); return n-n/2; }
  memcpy(dst,src,n); return 0;
}
static int cam_req_mgr_create_session(struct cam_req_mgr_session_info *s) {
  creates++; last_create=*s;
  if (backend_rc) return backend_rc;
  s->session_hdl=0x123456; return 0;
}
static int cam_req_mgr_destroy_session(struct cam_req_mgr_session_info *s, bool shutdown) {
  assert(!shutdown); destroys++; last_destroy=*s; return cleanup_rc;
}
static void reset(void) {
  input_fail=output_fail=backend_rc=cleanup_rc=0;
  creates=destroys=errors=infos=0; copyin_n=copyout_n=0;
  memset(&last_create,0,sizeof(last_create)); memset(&last_destroy,0,sizeof(last_destroy));
}
'''
tests = r'''
static unsigned checks;
#define CHECK(x) do { assert(x); checks++; } while (0)
int main(void) {
  _Static_assert(sizeof(struct cam_req_mgr_session_info)==8,"legacy ABI");
  _Static_assert(sizeof(struct cam_req_mgr_xiaomi_session_info)==12,"Xiaomi ABI");
  _Static_assert(offsetof(struct cam_req_mgr_xiaomi_session_info,is_check_concurrency)==4,"flag offset");
  _Static_assert(offsetof(struct cam_req_mgr_xiaomi_session_info,reserved)==8,"reserved offset");
  uint32_t words[5];
  struct cam_control cmd={.handle_type=1,.handle=(uint64_t)(uintptr_t)&words[1]};
  const uint32_t ops[]={CAM_REQ_MGR_CREATE_SESSION,CAM_REQ_MGR_DESTROY_SESSION};
  for(unsigned k=0;k<2;k++) for(uint32_t n=0;n<=24;n++) {
    if(n==8 || n==12) continue;
    reset(); cmd.op_code=ops[k]; cmd.size=n;
    CHECK(cam_private_ioctl(NULL,NULL,false,VIDIOC_CAM_CONTROL,&cmd)==-EINVAL);
    CHECK(creates==0 && destroys==0 && copyin_n==0 && copyout_n==0);
  }
  reset(); cmd.size=UINT32_MAX;
  CHECK(cam_private_ioctl(NULL,NULL,false,VIDIOC_CAM_CONTROL,&cmd)==-EINVAL);
  CHECK(copyin_n==0);
  for(unsigned k=0;k<2;k++) for(unsigned n=8;n<=12;n+=4) {
    reset(); memset(words,0xa5,sizeof(words)); words[1]=91;
    if(n==12) { words[2]=0; words[3]=0x13579; }
    else words[2]=0x13579;
    cmd.op_code=ops[k]; cmd.size=n;
    CHECK(cam_private_ioctl(NULL,NULL,false,VIDIOC_CAM_CONTROL,&cmd)==0);
    CHECK(copyin_n==n);
    CHECK(words[0]==0xa5a5a5a5 && words[4]==0xa5a5a5a5);
    CHECK(n==12 || words[3]==0xa5a5a5a5);
    if(k==0) {
      CHECK(creates==1 && destroys==0 && copyout_n==n && words[1]==0x123456);
      CHECK(last_create.reserved==0x13579 && last_create.session_hdl==91);
      if(n==12) CHECK(words[2]==0 && words[3]==0x13579);
    } else {
      CHECK(creates==0 && destroys==1 && copyout_n==0);
      CHECK(last_destroy.reserved==0x13579 && last_destroy.session_hdl==91);
    }
  }
  for(unsigned k=0;k<2;k++) for(unsigned n=8;n<=12;n+=4) {
    reset(); input_fail=1; cmd.op_code=ops[k]; cmd.size=n;
    CHECK(cam_private_ioctl(NULL,NULL,false,VIDIOC_CAM_CONTROL,&cmd)==-EFAULT);
    CHECK(creates==0 && destroys==0 && copyin_n==n && copyout_n==0);
  }
  const uint32_t flags[]={1,2,UINT32_MAX};
  for(unsigned f=0;f<3;f++) {
    reset(); cmd.op_code=CAM_REQ_MGR_CREATE_SESSION; cmd.size=12;
    words[1]=91; words[2]=flags[f]; words[3]=0x13579;
    CHECK(cam_private_ioctl(NULL,NULL,false,VIDIOC_CAM_CONTROL,&cmd)==-EOPNOTSUPP);
    CHECK(creates==0 && destroys==0 && copyout_n==0 && errors==1);
    reset(); cmd.op_code=CAM_REQ_MGR_DESTROY_SESSION;
    CHECK(cam_private_ioctl(NULL,NULL,false,VIDIOC_CAM_CONTROL,&cmd)==0);
    CHECK(destroys==1 && last_destroy.session_hdl==91);
  }
  const int failures[]={-ENOMEM,-EINVAL};
  for(unsigned i=0;i<2;i++) {
    reset(); backend_rc=failures[i]; cmd.op_code=CAM_REQ_MGR_CREATE_SESSION;
    cmd.size=12; words[2]=0;
    CHECK(cam_private_ioctl(NULL,NULL,false,VIDIOC_CAM_CONTROL,&cmd)==failures[i]);
    CHECK(creates==1 && destroys==0 && copyout_n==0);
  }
  for(unsigned i=0;i<2;i++) {
    reset(); output_fail=1; cleanup_rc=i?-ENOENT:0;
    cmd.op_code=CAM_REQ_MGR_CREATE_SESSION; cmd.size=12; words[2]=0;
    CHECK(cam_private_ioctl(NULL,NULL,false,VIDIOC_CAM_CONTROL,&cmd)==-EFAULT);
    CHECK(creates==1 && destroys==1 && last_destroy.session_hdl==0x123456);
    CHECK(copyout_n==12 && errors==i);
  }
  reset(); cmd.size=12; cmd.op_code=CAM_REQ_MGR_DESTROY_SESSION; cleanup_rc=-ENOENT;
  CHECK(cam_private_ioctl(NULL,NULL,false,VIDIOC_CAM_CONTROL,&cmd)==-ENOENT);
  CHECK(destroys==1 && copyout_n==0);
  reset(); cmd.handle=0;
  CHECK(cam_private_ioctl(NULL,NULL,false,VIDIOC_CAM_CONTROL,&cmd)==-EINVAL);
  CHECK(copyin_n==0);
  printf("%u assertions passed\n",checks);
  return 0;
}
'''
harness = prelude + helper + ioctl + tests
with tempfile.TemporaryDirectory(prefix='r61-camera-host-') as temporary:
    work = Path(temporary)
    (work/'candidate_harness.c').write_text(harness)
    cmd=['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-parameter',
         '-fsanitize=address,undefined','-fno-omit-frame-pointer',
         '-I',str(ROOT/'preimage/qcom/opensource/camera-kernel/include/uapi/camera'), str(work/'candidate_harness.c'),
         '-o',str(work/'candidate_harness')]
    p=subprocess.run(cmd,capture_output=True,text=True)
    if p.returncode:
        raise SystemExit(p.stderr)
    test_env=os.environ.copy()
    # This host disallows LeakSanitizer's /proc task walk. The harness allocates no
    # dynamic memory; address and undefined-behavior checks remain enabled.
    test_env['ASAN_OPTIONS']='detect_leaks=0'
    p=subprocess.run([str(work/'candidate_harness')],capture_output=True,text=True,env=test_env)
    if p.returncode:
        raise SystemExit(p.stderr+p.stdout)
report={
    'status':'PASS_HOST_HARNESS_ONLY',
    'stdout':p.stdout.strip(),
    'candidate_sha256':hashlib.sha256(src.encode()).hexdigest(),
    'harness_sha256':hashlib.sha256(harness.encode()).hexdigest(),
    'actual_helper_and_switch_arms_extracted':True,
    'sanitizers':['address','undefined'],
    'leak_sanitizer':'disabled: host /proc task walk denied; harness has no heap allocations',
    'checks':['strict invalid lengths including UINT32_MAX','8/12 byte exact copy lengths',
              'input partial copy fault causes no backend call','0-flag extended create',
              'nonzero extended create explicitly unsupported','extended destroy does not use concurrency flag',
              'reserved field translation and adjacent canaries','backend errno propagated',
              'failed extended copyout destroys newly created handle','cleanup error logged; EFAULT retained'],
    'limitations':['not a kernel build','not a device run','actual HAL wire size is not yet proven']
}
# Workflow saves stdout outside hash-locked inputs.
print(json.dumps(report,indent=2))
