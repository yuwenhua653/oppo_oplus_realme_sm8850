#!/usr/bin/env python3
"""Run the actual new diagnostic C code against bounded host I2C/sysfs mocks."""
from pathlib import Path
import hashlib,json,subprocess,tempfile,re

ROOT=Path(__file__).resolve().parent
block=(ROOT/'bq_diagnostic_block.c').read_text()
prefix=r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <sys/types.h>
#define module_param(...)
#define MODULE_PARM_DESC(...)
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define I2C_FUNC_SMBUS_READ_WORD_DATA 0x200000
enum { BQ_FG_REG_SOC, BQ_FG_REG_VOLT, BQ_FG_REG_TEMP };
static const unsigned char bq27z561_regs[]={0x2c,0x08,0x06};
struct device { void *of_node; };
struct i2c_adapter { bool capable; };
struct i2c_client { unsigned int addr; struct device dev; struct i2c_adapter *adapter; };
struct attribute { int mode; };
struct device_attribute { struct attribute attr; };
struct attribute_group { const char *name; struct attribute **attrs; };
#define DEVICE_ATTR_RO(n) struct device_attribute dev_attr_##n = {{0444}}
#define to_i2c_client(d) ((struct i2c_client *)((char *)(d)-offsetof(struct i2c_client,dev)))
static int reads[8],regs[8],nr_reads,add_count,add_ret;
static int i2c_smbus_read_word_data(struct i2c_client *c,unsigned char reg) { regs[nr_reads]=reg;return reads[nr_reads++]; }
static int i2c_check_functionality(struct i2c_adapter *a,int mask) { assert(mask==I2C_FUNC_SMBUS_READ_WORD_DATA);return a->capable; }
static int of_device_is_compatible(void *node,const char *str) { return !strcmp(node,str); }
#define dev_err_probe(dev,ret,...) (ret)
#define dev_info(...)
static int devm_device_add_group(struct device *dev,const struct attribute_group *g) { assert(!strcmp(g->name,"myron_readonly_gauge"));assert(g->attrs[0]->mode==0444);add_count++;return add_ret; }
#define sysfs_emit(buf,fmt,val) sprintf(buf,fmt,val)
static void reset(void) { nr_reads=add_count=add_ret=0; reads[0]=63;reads[1]=4044;reads[2]=2981; }
'''
source_root=ROOT/'preimage'
header=source_root/'drivers/power/supply/mca/mca_hardware_ic/fuelgauge_ic/bq27z561/inc/bq27z561.h'
header_text=header.read_text()
real_enum=re.search(r'enum bq_fg_reg_idx \{.*?\n\};',header_text,re.S).group(0)
real_regs=re.search(r'static u8 bq27z561_regs\[NUM_REGS\] = \{.*?\n\};',header_text,re.S).group(0)
prefix=prefix.replace('enum { BQ_FG_REG_SOC, BQ_FG_REG_VOLT, BQ_FG_REG_TEMP };\nstatic const unsigned char bq27z561_regs[]={0x2c,0x08,0x06};',
                      'typedef unsigned char u8;\n'+real_enum+'\n'+real_regs)
main=r'''
int main(void) {
 struct i2c_adapter a={true};
 struct i2c_client c={0x55,{"ti,bq27z561_master"},&a};
 char buf[128];int ret,scenarios=0;
 assert(!myron_readonly_diag);scenarios++;
 reset();c.addr=0x54;assert(bq_myron_diag_probe(&c)==-ENODEV);assert(!nr_reads&&!add_count);c.addr=0x55;scenarios++;
 reset();c.dev.of_node=NULL;assert(bq_myron_diag_probe(&c)==-ENODEV);assert(!nr_reads&&!add_count);scenarios++;
 reset();c.dev.of_node="ti,bq27z561_slave";assert(bq_myron_diag_probe(&c)==-ENODEV);assert(!nr_reads&&!add_count);c.dev.of_node="ti,bq27z561_master";scenarios++;
 reset();a.capable=false;assert(bq_myron_diag_probe(&c)==-EOPNOTSUPP);assert(!nr_reads&&!add_count);a.capable=true;scenarios++;
 for(int i=0;i<3;i++){reset();reads[i]=-EREMOTEIO;assert(bq_myron_diag_probe(&c)==-EREMOTEIO);assert(nr_reads==i+1&&!add_count);scenarios++;}
 reset();add_ret=-ENOMEM;assert(bq_myron_diag_probe(&c)==-ENOMEM);assert(nr_reads==3&&add_count==1);scenarios++;
 reset();assert(bq_myron_diag_probe(&c)==0);assert(nr_reads==3&&add_count==1);assert(regs[0]==0x2c&&regs[1]==8&&regs[2]==6);scenarios++;
 reset();ret=raw_soc_show(&c.dev,NULL,buf);assert(ret==3&&!strcmp(buf,"63\n"));assert(regs[0]==0x2c);scenarios++;
 reset();reads[0]=4044;assert(raw_voltage_mv_show(&c.dev,NULL,buf)==5);assert(!strcmp(buf,"4044\n")&&regs[0]==8);scenarios++;
 reset();reads[0]=2981;assert(raw_temperature_deci_kelvin_show(&c.dev,NULL,buf)==5);assert(!strcmp(buf,"2981\n")&&regs[0]==6);scenarios++;
 reset();reads[0]=-ESHUTDOWN;strcpy(buf,"untouched");assert(raw_soc_show(&c.dev,NULL,buf)==-ESHUTDOWN);assert(!strcmp(buf,"untouched"));scenarios++;
 reset();reads[0]=-EIO;strcpy(buf,"untouched");assert(raw_voltage_mv_show(&c.dev,NULL,buf)==-EIO);assert(!strcmp(buf,"untouched"));scenarios++;
 reset();reads[0]=-EREMOTEIO;strcpy(buf,"untouched");assert(raw_temperature_deci_kelvin_show(&c.dev,NULL,buf)==-EREMOTEIO);assert(!strcmp(buf,"untouched"));scenarios++;
 reset();reads[0]=0;assert(raw_soc_show(&c.dev,NULL,buf)==2&&!strcmp(buf,"0\n"));scenarios++;
 printf("{\"passed\":true,\"host_cases\":%d}\n",scenarios);
 return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='r61-bq-diag-') as td:
    p=Path(td);(p/'test.c').write_text(prefix+block+main)
    subprocess.run(['gcc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-unused-variable',str(p/'test.c'),'-o',str(p/'test')],check=True,capture_output=True)
    result=json.loads(subprocess.check_output([str(p/'test')],text=True))
# No stub for any hardware write, MCA provider or power_supply operation exists:
# if the actual diagnostic block called one, this -Werror compile would fail.
result.update({'test_scope':'Actual diagnostic C block with mock read-only I2C/sysfs; not a kernel build',
               'kernel_compilation':False,'target_hardware':False,
               'diagnostic_source_sha256':hashlib.sha256(block.encode()).hexdigest()})
gauge_rel='drivers/power/supply/mca/mca_hardware_ic/fuelgauge_ic/bq27z561/bq27z561.c'
candidate=(ROOT/'payload'/gauge_rel).read_text()
before=(ROOT/'preimage'/gauge_rel).read_text()
reverted=candidate.replace(block+'\n','',1)
reverted=reverted.replace('\tif (myron_readonly_diag)\n\t\treturn bq_myron_diag_probe(client);\n\n','',1)
assert reverted.count('\tif (myron_readonly_diag)\n\t\treturn 0;\n')==2
reverted=reverted.replace('\tif (myron_readonly_diag)\n\t\treturn 0;\n','')
reverted=reverted.replace('\tif (myron_readonly_diag) {\n\t\tdevm_device_remove_group(&client->dev, &bq_myron_diag_group);\n\t\treturn;\n\t}\n\n','',1)
assert reverted==before, 'Unintended legacy path change'
probe=candidate[candidate.index('static int bq_fg_probe('):candidate.index('static int bq_fg_suspend(')]
assert probe.index('return bq_myron_diag_probe(client)')<probe.index('devm_kzalloc(')<probe.index('bq_parse_dt(bq)')
remove=candidate[candidate.index('static void bq_fg_remove('):candidate.index('static void bq_fg_shutdown(')]
assert remove.index('devm_device_remove_group(')<remove.index('mutex_destroy(')
result['legacy_path_byte_preservation']=True
result['probe_branch_before_all_normal_allocation_and_hardware_setup']=True
result['remove_branch_before_normal_cleanup']=True
result['actual_register_header_sha256']=hashlib.sha256(header.read_bytes()).hexdigest()
# JSON is written by the workflow outside hash-locked source inputs.
print(json.dumps(result))
