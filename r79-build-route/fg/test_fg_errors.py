#!/usr/bin/env python3
"""Compile exact candidate functions; rejected original functions are negative controls."""
import pathlib, re, subprocess, tempfile, json
ROOT=pathlib.Path(__file__).resolve().parent
STR='drivers/power/supply/mca/mca_strategy/strategy_fg/mca_strategy_fg.c'
REG='drivers/power/supply/mca/mca_platform/mca_platform_fg_ic_ops.c'
def function(s,name):
    m=re.search(r'^(?:static )?(?:ssize_t|int) '+name+r'\([^;]*?\)\n\{',s,re.M)
    assert m,name
    pos=m.end(); depth=1
    while depth:
        depth += (s[pos]=='{')-(s[pos]=='}');pos+=1
    return s[m.start():pos]
base=r'''
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <stddef.h>
#include <errno.h>
#include <string.h>
#include <sys/types.h>
static int checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr,"check %d failed line %d: %s\n", checks,__LINE__,#x);exit(1); } } while(0)
#define mca_log_info(...) ((void)0)
#define mca_log_err(...) ((void)0)
'''
auth_prelude=r'''
enum {FG_PROP_MAIN_AUTH,FG_PROP_SLAVE_AUTH,FG_PROP_BATT_INDEX,FG_PROP_VERIFY_DIGEST,FG_PROP_BATT_POWER_MATCH,FG_PROP_FAKE_SOC,FG_PROP_FAKE_TEMP,FG_PROP_UPDATE_PERIOD,FG_PROP_DOD_COUNT,FG_PROP_ENABLE_ROLLBACK,FG_PROP_SELF_EQUAL_MAX_COUNT,FG_PROP_FIRST_USAGE_DATE};
enum {FG_IC_MASTER, FG_IC_SLAVE};
#define MCA_FG_TYPE_SINGLE_NUM_MAX 1
#define MCA_EVENT_TYPE_HW_INFO 0
#define MCA_EVENT_BATT_AUTH_PASS 1
#define MCA_EVENT_TYPE_BATTERY_INFO 2
#define MCA_EVENT_BATTERY_STS_CHANGE 3
#define STRATEGY_STATUS_TYPE_FG_FIRST_TERM 4
#define STRATEGY_STATUS_TYPE_FG_BATT_MATCH 5
#define FG_AUTH_ATTRS_SIZE 0
struct strategy_fg { struct { int fg_type,adapt_power,support_base_flip; } cfg; int batt_auth,batt_slave_auth,batt_index,fake_bap_match,update_period,monitor_work,fake_dod_count,enable_rollback,self_equal_max_count,first_termination; };
struct device {struct strategy_fg *data;};
struct device_attribute {struct {char *name;} attr;};
struct mca_sysfs_attr_info {int sysfs_attr_name;};
static struct mca_sysfs_attr_info selected;
static int strategy_fg_sysfs_field_tbl;
static int setter_ret,digest_ret,power_ret[2],power_val[2],notify_count,setter_calls,power_calls;
static void *dev_get_drvdata(struct device *d){return d->data;}
static struct mca_sysfs_attr_info *mca_sysfs_lookup_attr(const char *a,int b,int c){return &selected;}
static int kstrtoint(const char *s,int radix,int *v){char *e;*v=strtol(s,&e,radix);return *e?-EINVAL:0;}
static int platform_fg_ops_set_authentic(int role,int v){setter_calls++;return setter_ret;}
static int platform_fg_ops_set_verify_digest(int role,char *b){return digest_ret;}
static int platform_fg_ops_get_adapt_power(int role,int *v){power_calls++;*v=power_val[role];return power_ret[role];}
static void mca_event_block_notify(int a,int b,void *c){if(b==MCA_EVENT_BATT_AUTH_PASS)notify_count++;}
static void strategy_fg_set_fake_soc(struct strategy_fg *i,int v){}
static void strategy_fg_set_fake_temp(struct strategy_fg *i,int v){}
static void cancel_delayed_work_sync(int *w){}
static void mca_queue_delayed_work(int *w,int n){}
static int mca_strategy_set_first_usage_date(struct strategy_fg *i,const char*b){return 0;}
'''
auth_main=r'''
int main(void){
 struct strategy_fg f={.cfg={.fg_type=1,.adapt_power=67},.fake_bap_match=-1};
 struct device d={&f}; struct device_attribute a={0};
 int errors[]={-EOPNOTSUPP,-EIO,-ETIMEDOUT,-ENODEV};
 for(int role=0;role<2;role++)for(int i=0;i<4;i++){
  selected.sysfs_attr_name=role?FG_PROP_SLAVE_AUTH:FG_PROP_MAIN_AUTH;
  setter_ret=errors[i];notify_count=0;power_calls=0;f.batt_auth=f.batt_slave_auth=0;
  CHECK(strategy_fg_sysfs_store(&d,&a,"1",1)==errors[i]);
  CHECK(f.batt_auth==0&&f.batt_slave_auth==0);CHECK(notify_count==0);CHECK(power_calls==0);
 }
 setter_ret=0;f.cfg.fg_type=1;
 for(int i=0;i<4;i++){
  selected.sysfs_attr_name=FG_PROP_MAIN_AUTH;power_ret[0]=errors[i];power_val[0]=67;notify_count=0;
  CHECK(strategy_fg_sysfs_store(&d,&a,"1",1)==errors[i]);CHECK(notify_count==0);
  int match=42;CHECK(strategy_fg_check_battery_adapt_power(&f,&match)==errors[i]);CHECK(match==0);
  int status=42;CHECK(strategy_fg_get_status(STRATEGY_STATUS_TYPE_FG_BATT_MATCH,&status,&f)==errors[i]);CHECK(status==0);
 }
 f.cfg.fg_type=2;power_ret[0]=0;power_val[0]=power_val[1]=67;
 for(int i=0;i<4;i++){
  power_ret[1]=errors[i];int match=42;
  CHECK(strategy_fg_check_battery_adapt_power(&f,&match)==errors[i]);CHECK(match==0);
 }
 power_ret[0]=power_ret[1]=0;f.cfg.fg_type=1;notify_count=0;selected.sysfs_attr_name=FG_PROP_MAIN_AUTH;
 CHECK(strategy_fg_sysfs_store(&d,&a,"1",1)==1);CHECK(notify_count==1);CHECK(f.batt_auth==1);
 power_val[0]=55;notify_count=0;CHECK(strategy_fg_sysfs_store(&d,&a,"1",1)==1);CHECK(notify_count==0);
 power_val[0]=67;notify_count=0;CHECK(strategy_fg_sysfs_store(&d,&a,"0",1)==1);CHECK(notify_count==0);CHECK(f.batt_auth==0);
 f.cfg.fg_type=2;f.batt_auth=1;selected.sysfs_attr_name=FG_PROP_SLAVE_AUTH;notify_count=0;
 CHECK(strategy_fg_sysfs_store(&d,&a,"1",1)==1);CHECK(notify_count==1);
 selected.sysfs_attr_name=FG_PROP_VERIFY_DIGEST;
 for(int i=0;i<4;i++){digest_ret=errors[i];CHECK(strategy_fg_sysfs_store(&d,&a,"x",1)==errors[i]);}
 digest_ret=0;CHECK(strategy_fg_sysfs_store(&d,&a,"x",1)==1);
 puts("auth PASS");printf("checks=%d\n",checks);return 0;
}
'''
registry_prelude=r'''
#define FG_IC_MAX 2
#define GFP_KERNEL 0
#define MCA_FG_LEGACY_OPS_SIZE sizeof(struct fuelguage_ic_ops)
#define __rcu
#define DEFINE_MUTEX(x) int x
#define DEFINE_STATIC_SRCU(x) int x
#define mutex_lock(x) ((void)0)
#define mutex_unlock(x) ((void)0)
#define lockdep_is_held(x) 1
#define rcu_replace_pointer(p,n,c) ({__typeof__(p) old=(p); (p)=(n);old;})
#define rcu_access_pointer(p) (p)
#define rcu_assign_pointer(p,v) ((p)=(v))
#define rcu_dereference_protected(p,c) (p)
#define RCU_INIT_POINTER(p,v) ((p)=(v))
static int allocated,fail_alloc,drains;
static void *kmalloc(size_t n,int flags){if(fail_alloc)return NULL;void*p=malloc(n);if(p)allocated++;return p;}
static void kfree(void*p){if(p){allocated--;free(p);}}
static void synchronize_srcu(int *p){drains++;}
struct fuelguage_ic_ops {void *fn;};
struct fuelguage_info {void*data;struct fuelguage_ic_ops*ops;size_t ops_size;};
static struct fuelguage_info *g_fg_ic_ops[FG_IC_MAX];
static int platform_fg_lock,platform_fg_srcu;
'''
registry_main=r'''
int main(void){
 struct fuelguage_ic_ops a={0},b={0};int one,two;
 CHECK(platform_fg_ic_ops_register_size(2,&one,&a,sizeof(a))==-EOPNOTSUPP);CHECK(allocated==0);
 CHECK(platform_fg_ic_ops_register_size(0,NULL,&a,sizeof(a))==-EOPNOTSUPP);
 fail_alloc=1;CHECK(platform_fg_ic_ops_register_size(0,&one,&a,sizeof(a))==-ENOMEM);fail_alloc=0;
 CHECK(platform_fg_ic_ops_register_size(0,&one,&a,sizeof(a))==0);CHECK(allocated==1);
 CHECK(platform_fg_ic_ops_register_size(0,&two,&b,sizeof(b))==-EBUSY);CHECK(allocated==1);
 CHECK(g_fg_ic_ops[0]->data==&one&&g_fg_ic_ops[0]->ops==&a);
 CHECK(platform_fg_ic_ops_register_size(0,&one,&a,sizeof(a))==-EBUSY);CHECK(allocated==1);
 CHECK(platform_fg_ic_ops_unregister(0,&two,&b)==-ENOENT);CHECK(allocated==1);
 CHECK(g_fg_ic_ops[0]->data==&one);CHECK(drains==1);
 CHECK(platform_fg_ic_ops_register_size(1,&two,&b,sizeof(b))==0);CHECK(allocated==2);
 CHECK(platform_fg_ic_ops_unregister(0,&one,&a)==0);CHECK(g_fg_ic_ops[0]==NULL);CHECK(allocated==1);
 CHECK(platform_fg_ic_ops_register_size(0,&two,&b,sizeof(b))==0);CHECK(allocated==2);
 CHECK(platform_fg_ic_ops_unregister(0,&two,&b)==0);CHECK(platform_fg_ic_ops_unregister(1,&two,&b)==0);CHECK(allocated==0);
 puts("registry PASS");printf("checks=%d\n",checks);return 0;
}
'''
results=[]
with tempfile.TemporaryDirectory() as td:
 for variant in ['payload','preimage']:
  strategy=(ROOT/variant/STR).read_text();registry=(ROOT/variant/REG).read_text()
  cases={
   'auth':base+auth_prelude+'\n'+ '\n'.join(function(strategy,n) for n in ['strategy_fg_check_battery_adapt_power','strategy_fg_sysfs_store','strategy_fg_get_status'])+auth_main,
   'registry':base+registry_prelude+'\n'+'\n'.join(function(registry,n) for n in ['platform_fg_ic_ops_register_size','platform_fg_ic_ops_unregister'])+registry_main}
  for name,code in cases.items():
   src=pathlib.Path(td)/(variant+'-'+name+'.c');src.write_text(code);exe=src.with_suffix('')
   subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Wno-unused-parameter','-Wno-unused-variable','-Werror','-fsanitize=undefined','-g',str(src),'-o',str(exe)],check=True)
   p=subprocess.run([str(exe)],text=True,capture_output=True)
   expected=0 if variant=='payload' else 1
   assert p.returncode==expected,(variant,name,p.returncode,p.stdout,p.stderr)
   results.append(dict(variant=variant,test=name,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
report=dict(passed=True,scope='Exact extracted production functions, callback and SRCU synchronization stubs; no hardware or scheduler concurrency test',results=results)
(ROOT/'test-results.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
