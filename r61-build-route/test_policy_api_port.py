#!/usr/bin/env python3
"""Exercise actual zero-speed guards and CP capability preflight with failing providers."""
from pathlib import Path
import json,re,subprocess,tempfile,shutil
R=Path(__file__).resolve().parent
M=R/'payload/drivers/power/supply/mca/mca_strategy'
files=[M/'strategy_charger/mca_charger_thermal.c',M/'strategy_charger/mca_strategy_buckchg.c',M/'strategy_fg/mca_strategy_fg.c']
blocks=[]
for p in files:
 s=p.read_text();assert 'get_smem_battery_info' not in s
 blocks.extend(re.findall(r'int zero_speed = mca_qcom_smem_is_zero_speed\(\);\s*if \(zero_speed >= 0\)\s*is_zero_speed = zero_speed;',s))
assert len(blocks)==5
for path in [M/'strategy_charger/mca_strategy_quickchg.c',M/'strategy_wireless/mca_quick_wireless.c']:
 s=path.read_text();assert 'FG_IC_BASE' not in s and 'FG_IC_FLIP' not in s
 assert 'FG_IC_MASTER' in s and 'FG_IC_SLAVE' in s
 # Arrays and read sources consistently use the two role names; never increase FG_IC_MAX to fit donor slots 2/3.
 assert not re.search(r'#define\s+FG_IC_(?:MASTER|SLAVE|MAX)',s)
buck=files[1].read_text()
a=buck.index('\t/* Check optional chip capabilities before any reverse-mode writes. */');b=buck.index('\n\tif ((last_otg_present != otg_present)',a)
guard=buck[a:b]
assert all(x in guard for x in ['platform_class_cp_has_manual_revchg_mode','platform_class_cp_has_cp_reverse_mode'])
code=r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#define mca_log_err(...) ((void)0)
#define CP_ROLE_MASTER 0
#define CP_CHIP_VENDOR_BQ25960 1
#define CP_CHIP_VENDOR_SC8541 2
static int smem, vendor, vendor_rc, hardware_calls;
static bool supports_bq, supports_sc;
static int mca_qcom_smem_is_zero_speed(void) { return smem; }
static int platform_class_cp_get_chip_vendor(int role,int *out) { assert(role==0);*out=vendor;return vendor_rc; }
static bool platform_class_cp_has_cp_reverse_mode(int role) { assert(role==0);return supports_bq; }
static bool platform_class_cp_has_manual_revchg_mode(int role) { assert(role==0);return supports_sc; }
struct strategy_buckchg_dev { int cp_chip_vendor; };
'''
for i,block in enumerate(blocks):code+='static int smem_guard_'+str(i)+'(int is_zero_speed) {\n'+block+'\nreturn is_zero_speed;\n}\n'
code+='static void reverse_guard(struct strategy_buckchg_dev *info) { int ret;\n'+guard+'\n++hardware_calls;\n}\n'
code+='int main(void) {\n struct strategy_buckchg_dev info={0};\n'
for i in range(5):
 for initial in [0,1]:
  for value in [-19,-5,0,1]:
   expected=value if value>=0 else initial
   code+=f'smem={value};assert(smem_guard_{i}({initial})=={expected});\n'
code+=r'''
vendor_rc=-ENODEV;reverse_guard(&info);assert(hardware_calls==0);
vendor_rc=0;vendor=CP_CHIP_VENDOR_BQ25960;reverse_guard(&info);assert(hardware_calls==0);
vendor=CP_CHIP_VENDOR_SC8541;reverse_guard(&info);assert(hardware_calls==0);
vendor=3;reverse_guard(&info);assert(hardware_calls==1);
supports_bq=true;vendor=CP_CHIP_VENDOR_BQ25960;reverse_guard(&info);assert(hardware_calls==2);
supports_sc=true;vendor=CP_CHIP_VENDOR_SC8541;reverse_guard(&info);assert(hardware_calls==3);
return 0; }
'''
with tempfile.TemporaryDirectory(prefix='mca-policy-port-') as td:
 t=Path(td);(t/'test.c').write_text(code)
 subprocess.run([shutil.which('cc') or 'cc','-std=gnu11','-Wall','-Wextra','-Werror',str(t/'test.c'),'-o',str(t/'test')],check=True,capture_output=True,text=True)
 subprocess.run([str(t/'test')],check=True)
print(json.dumps({'status':'PASS','zero_speed_actual_sites':5,'zero_speed_scenarios':40,'reverse_capability_scenarios':6,'parallel_policy_slots':'MASTER=0 / SLAVE=1; donor BASE/FLIP absent','kernel_compiled':False},indent=2))
