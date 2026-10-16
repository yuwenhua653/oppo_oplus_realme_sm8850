#!/usr/bin/env python3
"""Compile actual CP/AICL source functions with failing-I/O fixtures; no kernel claim."""
from pathlib import Path
import json, os, re, shutil, subprocess, tempfile
R=Path(__file__).resolve().parent
M=Path('drivers/power/supply/mca')
def read(rel):return (R/'payload'/M/rel).read_text()
def function(text,name):
 m=re.search(r'(?m)^(?:static\s+)?(?:inline\s+)?(?:int|bool)\s+'+re.escape(name)+r'\s*\([^;]*?\)\s*\{',text)
 assert m,name
 i=m.end();depth=1
 while depth:
  if text[i]=='{':depth+=1
  if text[i]=='}':depth-=1
  i+=1
 return text[m.start():i]+'\n'
cp=read('mca_platform/mca_platform_cp_class.c');sc=read('mca_hardware_ic/charge_pump_ic/sc8581/sc8581.c')
buck=read('mca_platform/mca_platform_buckchg_class.c');proxy=read('mca_qcom_subpmic_proxy/mca_qcom_subpmic_proxy.c')
cpnames=['get_battery_vout','get_adc_enabled','set_busovp','enable_vbus_errorhi','enable_vbus_errorlo','set_manual_revchg_mode','set_cp_reverse_mode']
# Preserve every existing field's order; additions are source ABI changes, never stock-ABI compatibility.
for name,expected in [('platform_cp_class.h',7),('platform_buckchg_class.h',1)]:
 rel=M/'include/mca/platform'/name
 old=(R/'preimage'/rel).read_text();new=(R/'payload'/rel).read_text()
 fields=lambda s:re.findall(r'\(\*(\w+)\)',s)
 a,b=fields(old),fields(new)
 assert b[:len(a)]==a and len(b)==len(a)+expected
for name in ['cp_get_battery_vout','cp_get_adc_enabled','cp_set_busovp']:
 assert re.search(r'\.'+name+r'\s*=\s*ops_',sc)
for name in ['cp_enable_vbus_errorhi','cp_enable_vbus_errorlo','cp_set_manual_revchg_mode','cp_set_cp_reverse_mode']:
 assert not re.search(r'\.'+name+r'\s*=',sc)
code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include "platform_cp_class.h"
#include "platform_buckchg_class.h"
#define EXPORT_SYMBOL(x)
#define platform_cp_ops_invalid(data,name) (!data || !data->ops || !data->ops->name)
struct platform_cp_class_ops_data { struct platform_class_cp_ops *ops; void *data; unsigned int ops_size; };
static struct platform_cp_class_ops_data g_platform_cp_data[CP_ROLE_MAX];
#define cp_data g_platform_cp_data[0]
static struct platform_cp_class_ops_data *platform_cp_class_get_ic_ops(unsigned int role) {
 return role < CP_ROLE_MAX && cp_data.ops ? &cp_data : 0;
}
static int io_result, io_calls, adc_channel, threshold_seen;
static unsigned int io_value;
struct sc8581_device { void *client; int work_mode; };
#define SC8581_REG_15 0x15
#define SC8581_ADC_EN_MASK 0x80
#define CP_MODE_DIV_MAX 3
#define ADC_VOUT 7
static int cp_read_byte(void *client, u8 reg, u8 *val) { (void)client; assert(reg==SC8581_REG_15); ++io_calls; *val=io_value; return io_result; }
static int cp_get_adc_data(struct sc8581_device *bq, int channel, u32 *val) { (void)bq; ++io_calls; adc_channel=channel; *val=io_value; return io_result; }
static int sc8581_set_busovp_th(struct sc8581_device *bq, int threshold) { (void)bq; ++io_calls; threshold_seen=threshold; return io_result; }
'''
code+=cp[cp.index('#define platform_cp_ext_ops_invalid'):cp.index('\n\n',cp.index('#define platform_cp_ext_ops_invalid'))]+'\n'
code+=function(cp,'platform_class_cp_register_ops_v2')+function(cp,'platform_class_cp_register_ops')
code+='\n'.join(function(cp,'platform_class_cp_'+x) for x in cpnames+['has_manual_revchg_mode','has_cp_reverse_mode'])
code+='\n'.join(function(sc,x) for x in ['sc8581_check_adc_enabled','ops_cp_get_adc_enabled','ops_cp_get_vout','ops_cp_set_busovp'])
code+=r'''
struct platform_class_buckchg_data { void *data; struct platform_class_buckchg_ops *ops; unsigned int ops_size; };
static struct platform_class_buckchg_data *platform_buckchg_ops_data[MAX_BUCK_CHARGER];
static int platform_buckchg_srcu, locks, unlocks;
static int srcu_read_lock(int *x) { (void)x; ++locks; return 42; }
static void srcu_read_unlock(int *x,int idx) { (void)x; assert(idx==42);++unlocks; }
#define srcu_dereference(p,s) (p)
#define SUBPMIC_PROP_AICL_STATUS 0x2029
static int mca_adsp_glink_read_prop(int prop,int *val,unsigned long size) { assert(prop==SUBPMIC_PROP_AICL_STATUS && size==sizeof(int)); ++io_calls; *val=io_value; return io_result; }
'''
code+=function(buck,'platform_class_buckchg_ops_get_aicl_status')+function(proxy,'qcom_subpmic_get_aicl_status')
code+=r'''
static int callback_calls;
static int set_bool(bool value,void *data) { assert(value && data==&cp_data);++callback_calls;return -EIO; }
int main(void) {
 struct sc8581_device chip={.client=0,.work_mode=1};
 struct platform_class_cp_ops ops={.cp_get_battery_vout=ops_cp_get_vout,.cp_get_adc_enabled=ops_cp_get_adc_enabled,.cp_set_busovp=ops_cp_set_busovp};
 struct platform_class_buckchg_ops bops={.get_aicl_status=qcom_subpmic_get_aicl_status};
 struct platform_class_buckchg_data bdata={.data=0,.ops=&bops,.ops_size=sizeof(bops)};
 u32 out=123; bool enabled=false;int status=321;
 assert(platform_class_cp_get_battery_vout(0,&out)==-EOPNOTSUPP && out==123);
 assert(platform_class_cp_register_ops_v2(0,&ops,&chip,1)==-EINVAL);
 assert(platform_class_cp_register_ops_v2(0,&ops,&chip,sizeof(ops))==0);
 assert(platform_class_cp_get_battery_vout(CP_ROLE_MAX,&out)==-EOPNOTSUPP);
 assert(platform_class_cp_get_battery_vout(0,0)==-EINVAL);
 assert(platform_class_cp_get_adc_enabled(0,0)==-EINVAL);
 io_result=-EIO;io_value=88;
 assert(platform_class_cp_get_battery_vout(0,&out)==-EIO && out==123);
 assert(platform_class_cp_get_adc_enabled(0,&enabled)==-EIO && !enabled);
 io_result=0;io_value=3900;
 assert(platform_class_cp_get_battery_vout(0,&out)==0 && out==3900 && adc_channel==ADC_VOUT);
 io_value=SC8581_ADC_EN_MASK;
 assert(platform_class_cp_get_adc_enabled(0,&enabled)==0 && enabled);
 io_value=0;assert(platform_class_cp_get_adc_enabled(0,&enabled)==0 && !enabled);
 io_result=-EREMOTEIO;assert(platform_class_cp_set_busovp(0,11000)==-EREMOTEIO && threshold_seen==11000);
 io_calls=0;chip.work_mode=-1;assert(platform_class_cp_set_busovp(0,11000)==-EINVAL && !io_calls);
 chip.work_mode=CP_MODE_DIV_MAX;assert(platform_class_cp_set_busovp(0,11000)==-EINVAL && !io_calls);
 assert(!platform_class_cp_has_manual_revchg_mode(0) && !platform_class_cp_has_cp_reverse_mode(0));
 assert(platform_class_cp_enable_vbus_errorhi(0,true)==-EOPNOTSUPP);
 assert(platform_class_cp_enable_vbus_errorlo(0,true)==-EOPNOTSUPP);
 assert(platform_class_cp_set_manual_revchg_mode(0,true)==-EOPNOTSUPP);
 assert(platform_class_cp_set_cp_reverse_mode(0,true)==-EOPNOTSUPP);
 ops.cp_enable_vbus_errorhi=set_bool;ops.cp_enable_vbus_errorlo=set_bool;
 ops.cp_set_manual_revchg_mode=set_bool;ops.cp_set_cp_reverse_mode=set_bool;cp_data.data=&cp_data;
 assert(platform_class_cp_has_manual_revchg_mode(0) && platform_class_cp_has_cp_reverse_mode(0));
 assert(platform_class_cp_enable_vbus_errorhi(0,true)==-EIO);
 assert(platform_class_cp_enable_vbus_errorlo(0,true)==-EIO);
 assert(platform_class_cp_set_manual_revchg_mode(0,true)==-EIO);
 assert(platform_class_cp_set_cp_reverse_mode(0,true)==-EIO && callback_calls==4);
 assert(platform_class_buckchg_ops_get_aicl_status(MAX_BUCK_CHARGER,&status)==-EINVAL);
 assert(platform_class_buckchg_ops_get_aicl_status(0,0)==-EINVAL);
 assert(platform_class_buckchg_ops_get_aicl_status(0,&status)==-EOPNOTSUPP && status==321);
 platform_buckchg_ops_data[0]=&bdata;io_result=-EIO;io_value=999;
 assert(platform_class_buckchg_ops_get_aicl_status(0,&status)==-EIO && status==321);
 io_result=0;io_value=17;assert(platform_class_buckchg_ops_get_aicl_status(0,&status)==0 && status==17);
 assert(locks==unlocks && locks==3);
 assert(qcom_subpmic_get_aicl_status(0,0)==-EINVAL);
 { /* Exact legacy allocations: ASan catches any read of a new tail field. */
  size_t cp_size=offsetof(struct platform_class_cp_ops,cp_get_battery_vout);
  size_t buck_size=offsetof(struct platform_class_buckchg_ops,get_aicl_status);
  struct platform_class_cp_ops *legacy_cp=calloc(1,cp_size);
  struct platform_class_buckchg_ops *legacy_buck=calloc(1,buck_size);
  assert(legacy_cp && legacy_buck);
  assert(platform_class_cp_register_ops(0,legacy_cp,&chip)==0);
  assert(platform_class_cp_get_battery_vout(0,&out)==-EOPNOTSUPP);
  assert(!platform_class_cp_has_manual_revchg_mode(0));
  bdata.ops=legacy_buck;bdata.ops_size=buck_size;
  assert(platform_class_buckchg_ops_get_aicl_status(0,&status)==-EOPNOTSUPP);
  free(legacy_cp);free(legacy_buck);
 }
 return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='mca-provider-port-') as td:
 t=Path(td);(t/'linux').mkdir();(t/'linux/types.h').write_text('#include <stdint.h>\n#include <stdbool.h>\ntypedef uint8_t u8; typedef uint32_t u32;\n')
 for name in ['platform_cp_class.h','platform_buckchg_class.h']:(t/name).write_text(read('include/mca/platform/'+name))
 (t/'test.c').write_text(code)
 cmd=[shutil.which('cc') or 'cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(t),str(t/'test.c'),'-o',str(t/'test')]
 subprocess.run(cmd,check=True,capture_output=True,text=True);subprocess.run([str(t/'test')],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
print(json.dumps({'status':'PASS','scope':'Actual source functions with failure fixtures; source ABI tail/header and 3 hardware registrations checked. Kernel compile and hardware behavior not claimed.','assertions':code.count('assert('),'kernel_compiled':False},indent=2))
