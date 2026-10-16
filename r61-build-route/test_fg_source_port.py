#!/usr/bin/env python3
"""Compile actual changed C with controlled I/O faults. Not a kernel build."""
from pathlib import Path
import json,os,re,subprocess,sys,tempfile
OUT=Path(__file__).resolve().parent
P=OUT/'payload/drivers/power/supply/mca'
_temp=tempfile.TemporaryDirectory(prefix='r61-fg-source-port-')
T=Path(_temp.name)
header=(P/'include/mca/platform/platform_fg_ic_ops.h').read_text()
bq=(P/'mca_hardware_ic/fuelgauge_ic/bq27z561/bq27z561.c').read_text()
strategy=(P/'mca_strategy/strategy_fg/mca_strategy_fg.c').read_text()
dispatcher=(P/'mca_platform/mca_platform_fg_ic_ops.c').read_text()
def function(text,name):
 m=re.search(r'^(?:static\s+)?(?:inline\s+)?[\w\s*]+?\b'+re.escape(name)+r'\([^;]*?\)\s*\{',text,re.M)
 assert m,name
 start=m.start();i=m.end();depth=1
 while depth:
  if text[i]=='{':depth+=1
  elif text[i]=='}':depth-=1
  i+=1
 return text[start:i]+'\n'
hdr=re.sub(r'^#include.*\n','',header,flags=re.M)
common=r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <errno.h>
typedef uint8_t u8; typedef uint16_t u16; typedef int16_t s16; typedef uint32_t u32;
#define EPROBE_DEFER 517
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define mca_log_info(...) ((void)0)
#define mca_log_err(...) ((void)0)
'''+hdr
disp_stubs=r'''
#define __rcu
#define __init
#define __exit
#define EXPORT_SYMBOL(x)
#define MODULE_DESCRIPTION(x)
#define MODULE_AUTHOR(x)
#define MODULE_LICENSE(x)
#define DEFINE_MUTEX(x) int x
#define DEFINE_STATIC_SRCU(x) int x
#define GFP_KERNEL 0
static int reads,locks,syncs;
static void mutex_lock(int *p) {(void)p;locks++;}
static void mutex_unlock(int *p) {(void)p;locks--;assert(locks>=0);}
static int srcu_read_lock(int *p) {(void)p;reads++;return 0;}
static void srcu_read_unlock(int *p,int i) {(void)p;(void)i;reads--;assert(reads>=0);}
static void synchronize_srcu(int *p) {(void)p;syncs++;assert(!reads);}
#define srcu_dereference(p,s) (p)
#define rcu_dereference_protected(p,s) (p)
#define rcu_replace_pointer(p,n,s) ({__typeof__(p) old=(p);(p)=(n);old;})
#define RCU_INIT_POINTER(p,n) ((p)=(n))
static void *kmalloc(size_t n,int flags) {(void)flags;return malloc(n);}
#define kfree free
struct platform_driver {struct {const char *name;} driver;};
static int platform_driver_register(struct platform_driver *p) {(void)p;return 0;}
static void platform_driver_unregister(struct platform_driver *p) {(void)p;}
#define module_init(x) static void *used_init __attribute__((used)) = (void *)&x
#define module_exit(x) static void *used_exit __attribute__((used)) = (void *)&x
'''
disp_body=re.sub(r'^#include.*\n','',dispatcher,flags=re.M)
disp_test=r'''
_Static_assert(MCA_FG_LEGACY_OPS_SIZE==67*sizeof(void *),"legacy prefix changed");
_Static_assert(sizeof(struct fuelguage_ic_ops)==76*sizeof(void *),"v2 size");
_Static_assert(sizeof(struct mca_fg_abnormal_counts)==40,"typed count layout");
static int calls, fail;
static int read_int(void *p,int *v){assert(p);calls++;*v=123;return fail;}
static int read_date(void *p,u8 *v){assert(p);calls++;memcpy(v,"20261016",8);return fail;}
static int read_counts(void *p,struct mca_fg_abnormal_counts *v){assert(p);calls++;memset(v,7,sizeof(*v));return fail;}
static int write_op(void *p){assert(p);calls++;return fail;}
int main(void) {
 int data=1,v=99;u8 d[8];struct mca_fg_abnormal_counts c,saved;
 struct fuelguage_ic_ops ops={.fg_ic_get_average_current=read_int,
  .fg_ic_get_first_usage_date=read_date,.fg_ic_get_abnormal_counts=read_counts,
  .fg_ic_ota_update_check=write_op};
 struct fuelguage_ic_ops *old=calloc(1,MCA_FG_LEGACY_OPS_SIZE);
 assert(old);assert(platform_fg_ops_has_optional_op(0,MCA_FG_OP_OTA_UPDATE)==-EPROBE_DEFER);
 assert(platform_fg_ic_ops_register(0,&data,old)==0);
 assert(platform_fg_ops_has_optional_op(0,MCA_FG_OP_AVERAGE_CURRENT)==0);
 assert(platform_fg_ops_get_average_current(0,&v)==-EOPNOTSUPP && v==99);
 assert(platform_fg_ic_ops_unregister(0,&data,old)==0);free(old);
 assert(platform_fg_ic_ops_register_v2(0,&data,&ops,MCA_FG_LEGACY_OPS_SIZE)==-EINVAL);
 assert(platform_fg_ic_ops_register_v2(0,&data,&ops,sizeof(ops))==0);
 assert(platform_fg_ops_has_optional_op(0,MCA_FG_OP_OTA_UPDATE)==1 && calls==0);
 assert(platform_fg_ops_has_optional_op(0,MCA_FG_OP_QBG_CHG_DATA)==0 && calls==0);
 assert(platform_fg_ops_qbg_send_chg_data(0)==-EOPNOTSUPP);
 assert(platform_fg_ops_get_average_current(0,NULL)==-EINVAL);
 assert(platform_fg_ops_get_average_current(2,&v)==-EOPNOTSUPP && v==99);
 fail=-EIO;assert(platform_fg_ops_get_average_current(0,&v)==-EIO && v==99);
 memset(d,0xa5,sizeof(d));assert(platform_fg_ops_get_first_usage_date(0,d)==-EIO && d[0]==0xa5);
 memset(&c,0xa5,sizeof(c));saved=c;assert(platform_fg_ops_get_abnormal_counts(0,&c)==-EIO && !memcmp(&c,&saved,sizeof(c)));
 fail=0;assert(platform_fg_ops_get_average_current(0,&v)==0 && v==123);
 assert(platform_fg_ops_get_first_usage_date(0,d)==0 && !memcmp(d,"20261016",8));
 assert(platform_fg_ops_get_abnormal_counts(0,&c)==0 && c.ocd_count==0x07070707U);
 assert(platform_fg_ops_set_first_usage_date(0,"20261016")==-EOPNOTSUPP);
 assert(platform_fg_ic_ops_unregister(0,&data,&ops)==0);
 assert(!reads && !locks && syncs>=4);puts("dispatcher: PASS");return 0;
}
'''
(T/'dispatcher.c').write_text(common+disp_stubs+disp_body+disp_test)

bh=OUT/'preimage/drivers/power/supply/mca/mca_hardware_ic/fuelgauge_ic/bq27z561/inc/bq27z561.h'
bhtext=bh.read_text()
enums='\n'.join(re.search(r'enum '+n+r'\s*\{.*?\};',bhtext,re.S)[0] for n in ['bq_fg_reg_idx','bq_fg_mac_cmd'])
bq_stubs=r'''
#define INVALID_REG_ADDR 0xff
enum {PACK_SUPPLIER_BYD,PACK_SUPPLIER_COSLIGHT,PACK_SUPPLIER_SUNWODA,PACK_SUPPLIER_NVT,PACK_SUPPLIER_SCUD,PACK_SUPPLIER_TWS,PACK_SUPPLIER_LISHEN,PACK_SUPPLIER_DESAY};
struct i2c_client{int dummy;};
struct bq_fg_chip{struct i2c_client *client;u8 regs[NUM_REGS];int pm_suspend,data_lock,i2c_rw_lock;bool support_version_compatible;};
static int atomic_read(int *p){return *p;}
static int locks,wr_calls,rd_calls,wr_ret=1,rd_ret=2,word_ret=0,fail_read_at;
static u16 last_cmd,word=0xff9c;static int corrupt;static u8 custom[32];
static void mutex_lock(int *p){(void)p;locks++;}
static void mutex_unlock(int *p){(void)p;locks--;assert(locks>=0);}
static void usleep_range(int a,int b){(void)a;(void)b;}
static int __fg_write_block(struct i2c_client *c,u8 r,u8 *p,u8 n){(void)c;(void)r;assert(n==2);last_cmd=p[0]|(p[1]<<8);wr_calls++;return wr_ret;}
static int __fg_read_block(struct i2c_client *c,u8 r,u8 *p,u8 n){
 (void)c;(void)r;assert(n==36);rd_calls++;if(fail_read_at==rd_calls)return -EREMOTEIO;
 p[0]=(u8)last_cmd;p[1]=(u8)(last_cmd>>8);memcpy(p+2,custom,32);p[35]=36;
 if(last_cmd==FG_MAC_CMD_CUV_OCD || last_cmd==FG_MAC_CMD_HCUV_HOCD){for(unsigned i=0;i<32;i++)p[i+2]=(u8)(i+1);}
 unsigned sum=0;for(unsigned i=0;i<34;i++)sum+=p[i];p[34]=(u8)(255-(sum&255));
 if(corrupt==1)p[35]=3;
 if(corrupt==2)p[35]=42;
 if(corrupt==3)p[34]^=1;
 if(corrupt==4)p[0]^=1;
 return rd_ret;
}
static int fg_read_word(struct bq_fg_chip *bq,u8 reg,u16 *out){(void)bq;(void)reg;if(word_ret<0)return word_ret;*out=word;return word;}
'''
bq_functions='\n'.join(function(bq,n) for n in ['checksum','fg_mac_read_block_checked','fg_convert_u8_to_u16','fg_get_one_average_current','fg_read_first_usage_date','fg_read_manufacturing_date','fg_get_one_first_usage_date','fg_get_one_manufacturing_date','fg_get_pack_vendor_checked','fg_get_abnormal_counts'])
bq_test=r'''
static void reset(void){wr_ret=1;rd_ret=2;word_ret=0;wr_calls=rd_calls=fail_read_at=corrupt=0;memset(custom,0,32);assert(!locks);}
int main(void){struct i2c_client cl={0};struct bq_fg_chip bq={.client=&cl};u8 out[32],saved[32];int value;
 struct mca_fg_abnormal_counts c,cs;
 reset();memset(out,0xa5,32);memcpy(saved,out,32);
 bq.pm_suspend=1;assert(fg_mac_read_block_checked(&bq,1,out,8)==-EAGAIN && wr_calls==0);bq.pm_suspend=0;
 assert(fg_mac_read_block_checked(&bq,1,out,33)==-EINVAL);
 for(int ret=-EIO;ret<=0;ret+=EIO){reset();wr_ret=ret;assert(fg_mac_read_block_checked(&bq,1,out,8)<0 && rd_calls==0 && !memcmp(out,saved,32));}
 for(int ret=0;ret<2;ret++){reset();rd_ret=ret;assert(fg_mac_read_block_checked(&bq,1,out,8)==-EIO && !memcmp(out,saved,32));}
 for(int bad=1;bad<=4;bad++){reset();corrupt=bad;assert(fg_mac_read_block_checked(&bq,1,out,8)<0 && !memcmp(out,saved,32));}
 reset();custom[0]=0x42;assert(!fg_mac_read_block_checked(&bq,1,out,8) && out[0]==0x42);
 reset();value=77;word_ret=-EIO;assert(fg_get_one_average_current(&bq,&value)==-EIO && value==77);
 word_ret=0;assert(!fg_get_one_average_current(&bq,&value) && value==100);word=100;assert(!fg_get_one_average_current(&bq,&value) && value==-100);
 word=0x8000;assert(!fg_get_one_average_current(&bq,&value) && value==32768);
 bq.regs[NVT_FG_AVE_CUR]=255;value=77;assert(fg_get_one_average_current(&bq,&value)==-EOPNOTSUPP && value==77);
 reset();memset(out,0xa5,32);wr_ret=-EREMOTEIO;assert(fg_get_one_first_usage_date(&bq,out)==-EREMOTEIO && out[0]==0xa5);assert(fg_get_one_manufacturing_date(&bq,out)==-EREMOTEIO && out[0]==0xa5);
 reset();custom[11]=26;custom[12]=10;custom[13]=16;assert(!fg_get_one_first_usage_date(&bq,out) && !memcmp(out,"20261016",8));
 reset();custom[6]='6';custom[7]='A';custom[8]='1';custom[9]='6';assert(!fg_get_one_manufacturing_date(&bq,out) && !memcmp(out,"20261016",8));
 reset();value=77;custom[2]='?';assert(fg_get_pack_vendor_checked(&bq,&value)==-ENODATA && value==77);custom[2]='N';assert(!fg_get_pack_vendor_checked(&bq,&value) && value==PACK_SUPPLIER_NVT);
 reset();memset(&c,0xa5,sizeof(c));cs=c;fail_read_at=1;assert(fg_get_abnormal_counts(&bq,&c)==-EREMOTEIO && !memcmp(&c,&cs,sizeof(c)));
 reset();fail_read_at=2;assert(fg_get_abnormal_counts(&bq,&c)==-EREMOTEIO && !memcmp(&c,&cs,sizeof(c)));
 reset();assert(!fg_get_abnormal_counts(&bq,&c));assert(c.ocd_count==0x1e1d && c.ocd_last_cycle==0x201f && c.hocd_count==0x0e0d && c.hocd_last_cycle==0x100f && c.cuv_count==0x1211 && c.cuv_last_cycle==0x1413 && c.hcuv_count==0x0201 && c.hcuv_last_cycle==0x0403 && c.hscd_count==0x1211 && c.hscd_last_cycle==0x1413);
 assert(!locks);puts("BQ checked reads: PASS");return 0;}
'''
(T/'bq.c').write_text(common+enums+bq_stubs+bq_functions+bq_test)

strategy_stubs=r'''
#define MCA_FG_TYPE_SINGLE 0
#define MCA_FG_TYPE_PARALLEL 1
#define MCA_FG_TYPE_SINGLE_NUM_MAX 0
#define CHARGE_DFX_BATTERY_OCD 1
#define CHARGE_DFX_BATTERY_CUV 2
#define CHARGE_DFX_BATTERY_HSCD 3
struct device{int x;};struct work_struct{int x;};struct delayed_work{struct work_struct work;};
struct strategy_fg{struct device *dev;struct{int fg_type,support_nvt1000_ota,support_qbg;}cfg;bool support_battery_date;struct delayed_work batt_abnormal_dfx_work;int batt_ui_soc,batt_voltage,batt_temperature;};
#define to_delayed_work(p) ((struct delayed_work *)(p))
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
static int caps[9],hardware_calls,reads,writes,events,measure_ret,persist_ret,date_ret;
static int dev_err_probe(struct device*d,int ret,const char*f,...){(void)d;(void)f;return ret;}
int platform_fg_ops_has_optional_op(unsigned int role,enum mca_fg_optional_op op){assert(role==0);return caps[op];}
int platform_fg_ops_get_manufacturing_date(unsigned int role,u8 *v){(void)role;memcpy(v,"20261016",8);return date_ret;}
int platform_fg_ops_get_first_usage_date(unsigned int role,u8 *v){(void)role;memcpy(v,"20261016",8);return date_ret;}
int platform_fg_ops_set_first_usage_date(unsigned int role,const char*v){(void)role;(void)v;hardware_calls++;return -EOPNOTSUPP;}
int platform_fg_ops_get_abnormal_counts(unsigned int role,struct mca_fg_abnormal_counts *v){assert(role==0);v->ocd_count=1;v->ocd_last_cycle=2;v->hocd_count=3;v->hocd_last_cycle=4;v->cuv_count=5;v->cuv_last_cycle=6;v->hcuv_count=7;v->hcuv_last_cycle=8;v->hscd_count=9;v->hscd_last_cycle=10;return measure_ret;}
static int charger_partition_read_ocd_count(u32 *a,u32*b){reads++;*a=*b=0;return persist_ret;}
static int charger_partition_read_cuv_count(u32 *a,u32*b){reads++;*a=*b=0;return persist_ret;}
static int charger_partition_read_hscd_count(u32 *a){reads++;*a=0;return persist_ret;}
static int charger_partition_write_ocd_count(u32 a,u32 b){assert(a==1&&b==3);writes++;return 0;}
static int charger_partition_write_cuv_count(u32 a,u32 b){assert(a==5&&b==7);writes++;return 0;}
static int charger_partition_write_hcsd_count(u32 a){assert(a==9);writes++;return 0;}
static void mca_charge_mievent_report(int event,int *report,int count){(void)event;(void)report;(void)count;events++;}
'''
strategy_funcs='\n'.join(function(strategy,n) for n in ['strategy_fg_require_optional_op','strategy_fg_check_optional_ops','mca_strategy_get_manufacturing_date','mca_strategy_get_first_usage_date','mca_strategy_set_first_usage_date','strategy_batt_abnormal_dfx_work'])
strategy_test=r'''
int main(void){struct strategy_fg f={0};char d[9]="original";
 assert(!strategy_fg_check_optional_ops(&f) && hardware_calls==0);
 f.cfg.support_nvt1000_ota=1;assert(strategy_fg_check_optional_ops(&f)==-EOPNOTSUPP && hardware_calls==0);
 caps[MCA_FG_OP_OTA_FLAG]=caps[MCA_FG_OP_AVERAGE_CURRENT]=1;assert(strategy_fg_check_optional_ops(&f)==-EOPNOTSUPP && hardware_calls==0);
 caps[MCA_FG_OP_OTA_UPDATE]=1;assert(!strategy_fg_check_optional_ops(&f) && hardware_calls==0);
 f.cfg.support_qbg=1;assert(strategy_fg_check_optional_ops(&f)==-EOPNOTSUPP && hardware_calls==0);caps[MCA_FG_OP_QBG_CHG_DATA]=-EPROBE_DEFER;assert(strategy_fg_check_optional_ops(&f)==-EPROBE_DEFER);
 f.support_battery_date=true;date_ret=-EIO;assert(mca_strategy_get_manufacturing_date(&f,d)==-EIO && !strcmp(d,"original"));assert(mca_strategy_get_first_usage_date(&f,d)==-EIO && !strcmp(d,"original"));assert(mca_strategy_set_first_usage_date(&f,"20261016")==-EOPNOTSUPP);
 measure_ret=-EREMOTEIO;strategy_batt_abnormal_dfx_work(&f.batt_abnormal_dfx_work.work);assert(!reads && !writes && !events);
 measure_ret=0;persist_ret=-EROFS;strategy_batt_abnormal_dfx_work(&f.batt_abnormal_dfx_work.work);assert(reads==1 && !writes && !events);
 reads=0;persist_ret=0;strategy_batt_abnormal_dfx_work(&f.batt_abnormal_dfx_work.work);assert(reads==3 && writes==3 && events==3);
 puts("strategy failures/capabilities: PASS");return 0;}
'''
(T/'strategy.c').write_text(common+strategy_stubs+strategy_funcs+strategy_test)
results=[]
for name in ['dispatcher','bq','strategy']:
 args=['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wformat=2','-g','-fsanitize=address,undefined',str(T/(name+'.c')),'-o',str(T/name)]
 r=subprocess.run(args,text=True,capture_output=True)
 if r.returncode:print(r.stderr,file=sys.stderr);sys.exit(r.returncode)
 env=os.environ.copy();env['ASAN_OPTIONS']='detect_leaks=0'
 r=subprocess.run([str(T/name)],text=True,capture_output=True,env=env)
 if r.returncode:
  print(r.stdout+r.stderr,file=sys.stderr);sys.exit(r.returncode)
 results.append(dict(test=name,passed=True,compile=args,stdout=r.stdout.strip()))
print(json.dumps({'success':True,'scope':'Actual production C extracted with controlled kernel/I2C stubs; not a full kernel compile or SRCU concurrency validation.','sanitizers':['address','undefined'],'leak_detection':False,'results':results},indent=2))
_temp.cleanup()
