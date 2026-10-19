#!/usr/bin/env python3
"""Focused production-C control-flow checks; no kernel build or device access."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def function(text, name):
    at = text.index(name + '(')
    start = text.rfind('\n', 0, at) + 1
    opening = text.index('{', at)
    depth = 1
    pos = opening + 1
    while depth:
        depth += (text[pos] == '{') - (text[pos] == '}')
        pos += 1
    return text[start:pos]


def run_c(directory, name, source):
    path = directory / (name + '.c')
    path.write_text(source)
    exe = directory / name
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                    '-Wno-unused-variable', '-fsanitize=undefined', '-fno-sanitize-recover=all',
                    str(path), '-o', str(exe)], check=True, capture_output=True, text=True)
    subprocess.run([str(exe)], check=True, capture_output=True, text=True)


MACHINE_FIXTURE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <errno.h>
#define EPROBE_DEFER 517
#define GFP_KERNEL 0
#define BIT(n) (1U << (n))
#define LPASS_BE_PRI_TDM_RX_0 "rx"
#define LPASS_BE_PRI_TDM_TX_0 "tx"
#define module_param(a,b,c)
#define MODULE_PARM_DESC(a,b)
typedef uint32_t u32;
struct device_node { int available, compatible, reg_error, refs; u32 address; int index; };
struct device { struct device_node *of_node; };
struct i2c_adapter { int nr; };
struct i2c_client { struct device dev; unsigned short addr; struct i2c_adapter *adapter; };
struct snd_soc_dai_link_component { const char *name, *dai_name; struct device_node *of_node; };
struct snd_soc_dai_link { const char *name; struct snd_soc_dai_link_component *codecs; int num_codecs; };
struct snd_soc_card { struct device *dev; struct snd_soc_dai_link *dai_link; int num_links; };
static struct device_node nodes[4], card_node;
static struct i2c_client clients[4];
static struct i2c_adapter adapters[4];
static int node_count, missing_client, action_fail, nactions, nalloc, puts_count;
static void *allocated[20];
static struct { void (*fn)(void *); void *data; } actions[12];
static void of_node_put(void *value) { struct device_node *n=value; if(n) { assert(n->refs>0); n->refs--; } }
static struct device_node *of_node_get(struct device_node *n) { n->refs++; return n; }
static struct device_node *next_node(struct device_node *previous) {
 int n=previous ? previous->index+1 : 0; if(previous)of_node_put(previous);
 if(n>=node_count)return NULL;
 return of_node_get(&nodes[n]);
}
#define for_each_compatible_node(n,t,c) for((n)=next_node(NULL);(n);(n)=next_node(n))
static int of_device_is_compatible(struct device_node *n,const char *s) { return n->compatible; }
static int of_device_is_available(struct device_node *n) { return n->available; }
static int of_property_read_u32(struct device_node *n,const char *s,u32 *out) { *out=n->address; return n->reg_error; }
static struct i2c_client *of_find_i2c_device_by_node(struct device_node *n) { return n->index==missing_client ? NULL : &clients[n->index]; }
static void put_device(struct device *d) { puts_count++; }
static void *devm_kcalloc(struct device *d,int n,size_t sz,int g) { void *p=calloc(n,sz); allocated[nalloc++]=p; return p; }
static char *devm_kasprintf(struct device *d,int g,const char *fmt,...) {
 char *s=malloc(80); va_list ap; va_start(ap,fmt); vsnprintf(s,80,fmt,ap); va_end(ap); allocated[nalloc++]=s; return s;
}
static int devm_add_action_or_reset(struct device *d,void (*fn)(void *),void *data) {
 if(action_fail) { fn(data); return -ENOMEM; } actions[nactions].fn=fn; actions[nactions++].data=data; return 0;
}
static void clear(void) {
 for(int i=nactions-1;i>=0;i--)actions[i].fn(actions[i].data);
 for(int i=0;i<nalloc;i++)free(allocated[i]);
 for(int i=0;i<4;i++)assert(nodes[i].refs==0);
 nactions=nalloc=0;
}
static void setup(void) {
 memset(nodes,0,sizeof(nodes)); node_count=3; missing_client=-1; action_fail=0; puts_count=0;
 card_node.compatible=1;
 for(int i=0;i<4;i++) { nodes[i].index=i; nodes[i].address=0x34+i; nodes[i].available=1;
  adapters[i].nr=13; clients[i].addr=0x34+i; clients[i].adapter=&adapters[i]; }
}
'''


MACHINE_MAIN = r'''
int main(void) {
 struct device dev={.of_node=&card_node};
 struct snd_soc_dai_link_component old={0};
 struct snd_soc_dai_link links[2]={{"rx",&old,1},{"tx",&old,1}};
 struct snd_soc_card card={&dev,links,2};
 setup(); myron_tfa_links=false; assert(myron_tfa_configure_links(&card)==0); assert(nalloc==0);
 myron_tfa_links=true; assert(myron_tfa_configure_links(&card)==0);
 assert(links[0].num_codecs==3 && links[1].num_codecs==3 && links[0].codecs==links[1].codecs);
 for(int i=0;i<3;i++){char expected[40];snprintf(expected,sizeof(expected),"tfa98xx-aif-d-%x",0x34+i);assert(!strcmp(links[0].codecs[i].dai_name,expected));}
 assert(puts_count==3); clear();
 for(int test=0;test<8;test++) {
  setup(); links[0].codecs=&old;links[1].codecs=&old;links[0].num_codecs=links[1].num_codecs=1;
  if(test==0)nodes[2].address=0x34;
  if(test==1)node_count=2;
  if(test==2)missing_client=1;
  if(test==3)adapters[2].nr=14;
  if(test==4)nodes[2].available=0;
  if(test==5)nodes[2].address=0x40;
  if(test==6)action_fail=1;
  if(test==7)card_node.compatible=0;
  assert(myron_tfa_configure_links(&card)<0);
  assert(links[0].codecs==&old && links[1].codecs==&old && links[0].num_codecs==1 && links[1].num_codecs==1);
  clear();
 }
 return 0;
}
'''


PIN_FIXTURE = r'''
#include <assert.h>
#include <errno.h>
struct pinctrl { int dummy; }; struct pinctrl_state { int n; };
struct tfa98xx { struct pinctrl *rcv_pinctrl; struct pinctrl_state *rcv_gpio_high,*rcv_gpio_low; int spk_sw_gpio,spk_sw_level,dsp_lock; };
static int fail,selected=-1,calls,locks;
static void mutex_lock(int *m){locks++;} static void mutex_unlock(int *m){locks--;}
static int pinctrl_select_state(struct pinctrl *p,struct pinctrl_state *s){calls++;selected=s->n;return fail;}
static int gpio_is_valid(int n){return n>=0;}
static int gpio_direction_output(int n,int level){calls++;selected=level;return fail;}
'''


PIN_MAIN = r'''
int main(void) {
 struct pinctrl p; struct pinctrl_state high={1},low={0};
 struct tfa98xx t={&p,&high,&low,-1,-ENODATA,0};
 assert(tfa98xx_set_spksw(&t,2)==-EINVAL && calls==0);
 assert(tfa98xx_set_spksw(&t,1)==0 && selected==1 && t.spk_sw_level==1);
 fail=-EIO;assert(tfa98xx_set_spksw(&t,0)==-EIO && t.spk_sw_level==1);
 fail=0;assert(tfa98xx_set_spksw(&t,0)==0 && selected==0 && t.spk_sw_level==0);
 t.rcv_pinctrl=0;assert(tfa98xx_set_spksw(&t,1)==-ENODEV && t.spk_sw_level==0);
 t.spk_sw_gpio=27;assert(tfa98xx_set_spksw(&t,1)==0 && selected==1 && t.spk_sw_level==1);
 assert(locks==0);return 0;
}
'''


REV_FIXTURE = r'''
#include <assert.h>
#include <errno.h>
enum Tfa98xx_Error { Tfa98xx_Error_Ok=0, Tfa98xx_Error_NotOpen=1 };
struct tfa_device { int in_use,rev,revid; unsigned short interrupt_enable[1]; };
static int wait_error,write_count,regs[256];
#define pr_err(...) ((void)0)
#define pr_info(...) ((void)0)
#define TFA_BF_MSK(n) (1U << ((n) & 7))
static int tfa_set_bf(struct tfa_device *t,int b,int v){return 0;}
static int tfa_wait4manstate(struct tfa_device *t,int b,int v,int n){return wait_error;}
static int tfa_get_bf(struct tfa_device *t,int b){return b==0xf3b1 || b==0x0687;}
static int tfa_reg_write(struct tfa_device *t,int reg,int v){write_count++;regs[reg]=v;return 0;}
static int tfa_reg_read(struct tfa_device *t,int reg,unsigned short *v){*v=0;return 0;}
static void tfa98xx_key2(struct tfa_device *t,int v){}
static void tfa_irq_init(struct tfa_device *t){}
'''


REV_MAIN = r'''
int main(void) {
 struct tfa_device t={.in_use=0,.rev=0xb66};
 assert(tfa986x_specific(&t)==Tfa98xx_Error_NotOpen && write_count==0);
 t.in_use=1;wait_error=-ETIMEDOUT;
 assert((int)tfa986x_specific(&t)==-ETIMEDOUT && write_count==0);
 wait_error=0;
 assert(tfa986x_specific(&t)==Tfa98xx_Error_Ok && t.revid==0x110b65);
 /* Two key writes plus the exact twenty-write upstream MN2B0 table. */
 assert(write_count==22 && regs[0x02]==0x0c28 && regs[0x54]==0x10e0 && regs[0x62]==0x06c4 && regs[0x7c]==0x10f2);
 assert(t.interrupt_enable[0]!=0);
 return 0;
}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    spec=importlib.util.spec_from_file_location('audio_apply',root/'apply.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    checked=module.check(root)
    tests=[]
    with tempfile.TemporaryDirectory(prefix='r78-audio-') as d:
        temp=Path(d)
        machine=(root/'payload-modules/qcom/opensource/audio-kernel/asoc/audio_machine.c').read_text()
        helper=machine[machine.index('static bool myron_tfa_links;'):machine.index('static int msm_populate_dai_link_component_of_node(')]
        run_c(temp,'machine',MACHINE_FIXTURE+helper+MACHINE_MAIN)
        tests.append('production machine C: opt-out, three dynamic DAIs, eight no-partial-link failures, OF reference release')
        driver=(root/'payload/drivers/xiaomi/myron_tfa98xx/src/tfa98xx.c').read_text()
        run_c(temp,'pinctrl',PIN_FIXTURE+function(driver,'tfa98xx_set_spksw')+PIN_MAIN)
        tests.append('production receiver C: declared states, invalid values, failure preserves cached state, missing GPIO refusal')
        init=(root/'payload/drivers/xiaomi/myron_tfa98xx/src/tfa_init.c').read_text()
        specific=function(init,'tfa986x_specific')
        macros=''.join('#define '+name+' '+str(i+1)+'\n' for i,name in
                       enumerate(sorted(set(re.findall(r'TFA986X_BF_[A-Z0-9]+',specific)))))
        run_c(temp,'revision',REV_FIXTURE+macros+specific+REV_MAIN)
        tests.append('production MN2B0 C: raw revision/type mapping, exact B table, not-open/timeout refusal and interrupt mask retained')
        contract=json.loads((root/'contract.json').read_text())
        workspace=temp/'workspace'
        for row in contract['writes']:
            if row['before_sha256']:
                dest=workspace/row['destination'];dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(root/row['preimage'],dest)
        module.apply(workspace,root); module.apply(workspace,root,verify=True)
        assert module.apply(workspace,root)['changed']==0
        # Check the entire plan before any new source write.
        shutil.rmtree(workspace)
        for row in contract['writes']:
            if row['before_sha256']:
                dest=workspace/row['destination'];dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(root/row['preimage'],dest)
        bad=next(r for r in contract['writes'] if r['mode']=='append')
        (workspace/bad['destination']).write_bytes(b'unexpected preimage\n')
        try:module.apply(workspace,root)
        except ValueError:pass
        else:raise AssertionError('Unexpected preimage accepted')
        assert not any((workspace/r['destination']).exists() for r in contract['writes'] if r['mode']=='new')
        tests.append('exact complete apply/verify/idempotence and unexpected-preimage failure before any payload write')
    result={'schema':1,'status':'PASS_LOCAL_SOURCE_AND_CONTROL_FLOW','tests':tests,
            'compiled_kernel_module':False,'hardware_tested':False,'runtime_loading_approved':False,
            'contract_sha256':hashlib.sha256((root/'contract.json').read_bytes()).hexdigest()}
    if args.output:args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
