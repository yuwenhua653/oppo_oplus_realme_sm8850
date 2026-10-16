#!/usr/bin/env python3
"""Execute actual extracted source lookup; no sensor or regulator is accessed."""
from pathlib import Path
import re, subprocess, json, os, tempfile
ROOT=Path(__file__).resolve().parent
REL='qcom/opensource/camera-kernel/drivers/cam_sensor_module/cam_sensor_utils'
BASE=ROOT/'preimage'/REL
CAND=ROOT/'payload'/REL

def extract_enum(h,name):
    return re.search(r'enum '+name+r'\s*\{.*?\};',h,re.S).group(0)

pre='''#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
#include <assert.h>
#define CAM_SOC_MAX_REGULATOR 32
#define INVALID_VREG 100
#define CAM_BYPASS_RGLTR 1
#define CAM_ERR(...) ((void)0)
#define CAM_DBG(...) ((void)0)
#define VALIDATE_VOLTAGE(min,max,v) ((v) && (v)>=(min) && (v)<=(max))
static unsigned debug_bypass_drivers;
struct cam_hw_soc_info {int num_rgltr; const char *rgltr_name[32]; int rgltr_min_volt[32],rgltr_max_volt[32];};
'''
body='''
struct cam_sensor_power_setting { enum msm_camera_power_seq_type seq_type; unsigned short seq_val; long config_val; unsigned short delay; void *data[10]; bool valid_config; };
'''
test='''
int main(void) {
  struct cam_hw_soc_info soc={.num_rgltr=4,.rgltr_name={"cam_vana1","cam_bob","cam_bob2","cam_v_custom3"},.rgltr_min_volt={100,200,200,500},.rgltr_max_volt={100,400,400,500}};
  struct cam_sensor_power_setting p={.seq_type=(enum msm_camera_power_seq_type)14,.config_val=100};
  if (SENSOR_SEQ_TYPE_MAX==14) {
    assert(msm_camera_fill_vreg_params(&soc,&p,1)==-EINVAL);
    puts("baseline rejects wire value14"); return 0;
  }
  assert(CAM_BOB==7 && CAM_BOB2==8 && CAM_CLK==9 && CAM_VREG_MAX==10);
  assert(SENSOR_BOB==12 && SENSOR_BOB2==13 && SENSOR_VANA1==14 && SENSOR_CUSTOM_REG3==15 && SENSOR_SEQ_TYPE_MAX==16);
  assert(msm_camera_fill_vreg_params(&soc,&p,1)==0 && p.seq_val==0 && p.valid_config && p.config_val==100);
  p=(struct cam_sensor_power_setting){.seq_type=SENSOR_BOB,.config_val=300};
  assert(msm_camera_fill_vreg_params(&soc,&p,1)==0 && p.seq_val==1 && p.valid_config);
  p=(struct cam_sensor_power_setting){.seq_type=SENSOR_BOB2,.config_val=350};
  assert(msm_camera_fill_vreg_params(&soc,&p,1)==0 && p.seq_val==2 && p.valid_config);
  p=(struct cam_sensor_power_setting){.seq_type=SENSOR_CUSTOM_REG3,.config_val=500};
  assert(msm_camera_fill_vreg_params(&soc,&p,1)==0 && p.seq_val==3 && p.valid_config);
  p=(struct cam_sensor_power_setting){.seq_type=SENSOR_VANA1,.config_val=101};
  assert(msm_camera_fill_vreg_params(&soc,&p,1)==0 && p.seq_val==0 && !p.valid_config && p.config_val==101);
  p=(struct cam_sensor_power_setting){.seq_type=SENSOR_BOB2}; soc.rgltr_name[2]="absent";
  assert(msm_camera_fill_vreg_params(&soc,&p,1)==0 && p.seq_val==INVALID_VREG && !p.valid_config);
  p=(struct cam_sensor_power_setting){.seq_type=(enum msm_camera_power_seq_type)16};
  assert(msm_camera_fill_vreg_params(&soc,&p,1)==-EINVAL);
  p.seq_type=(enum msm_camera_power_seq_type)-1;assert(msm_camera_fill_vreg_params(&soc,&p,1)==-EINVAL);
  assert(msm_camera_fill_vreg_params(0,&p,1)==-EINVAL);
  assert(msm_camera_fill_vreg_params(&soc,0,1)==-EINVAL);
  soc.num_rgltr=0;assert(msm_camera_fill_vreg_params(&soc,&p,1)==-EINVAL);
  puts("11 candidate lookup assertions passed");
}
'''
results=[]
with tempfile.TemporaryDirectory(prefix='camera-power-abi-') as temp:
 work=Path(temp)
 for name,path in [('base',BASE),('candidate',CAND)]:
     h=(path/'cam_sensor_cmn_header.h').read_text();c=(path/'cam_sensor_util.c').read_text()
     st=c.index('int32_t msm_camera_fill_vreg_params(');en=c.index('int cam_sensor_util_request_gpio_table',st)
     enum=extract_enum(h,'msm_camera_power_seq_type')+'\n'+extract_enum(h,'msm_camera_vreg_name_t')
     # Identifiers are absent from the old enum, so test binary needs aliases in
     # the unreachable candidate branch. They don't affect the base function.
     compat='#define SENSOR_BOB 98\n#define SENSOR_BOB2 99\n#define CAM_BOB 98\n#define CAM_BOB2 99\n' if name=='base' else ''
     source=pre+enum+'\n'+compat+body+c[st:en]+test
     p=work/(name+'-lookup-test.c');p.write_text(source)
     output=work/(name+'-lookup-test')
     subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=undefined,address',str(p),'-o',str(output)],check=True)
     # LeakSanitizer cannot enumerate the container's hidden /proc tasks.
     test_env=os.environ.copy();test_env['ASAN_OPTIONS']='detect_leaks=0'
     r=subprocess.run([str(output)],check=True,text=True,capture_output=True,env=test_env)
     results.append({'name':name,'result':r.stdout.strip(),'kernel_hardware_execution':False})

base=(BASE/'cam_sensor_util.c').read_text();cand=(CAND/'cam_sensor_util.c').read_text()
# Three power paths must include both new regulators. Removing the reviewed
# lookup block and added case labels must reproduce the complete base file.
up=cand[cand.index('int cam_sensor_core_power_up('):cand.index('int cam_sensor_util_power_down(')]
powerup,unwind=up.split('power_up_failed:',1)
down=cand[cand.index('int cam_sensor_util_power_down('):]
for path in [powerup,unwind,down]:
    assert path.count('case SENSOR_BOB:')==path.count('case SENSOR_BOB2:')==1
lookup_start=cand.index('\t\tcase SENSOR_BOB:')
lookup_end=cand.index('\t\tdefault:',lookup_start)
rest=cand[:lookup_start]+cand[lookup_end:]
assert rest.replace('\t\tcase SENSOR_BOB:\n\t\tcase SENSOR_BOB2:\n','')==base
results.append({'name':'powerup_unwind_powerdown_static_scope',
                'result':'Both case labels in all three paths; all remaining util source is byte-identical to base after removing the new lookup block and case labels.',
                'hardware_execution':False})
print(json.dumps({'status':'PASS','limit':'Host lookup behavior and enum checks only; no kernel build, power sequence hardware or runtime ABI proof. Synthetic regulator fixtures contain no device-derived data.','results':results},indent=2))
