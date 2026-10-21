#!/usr/bin/env python3
"""Compile and test exact production helper bodies using fake I/O boundaries."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REL = Path('drivers/power/supply/mca/mca_hardware_ic/fuelgauge_ic/bq27z561/bq27z561.c')
REPO = ROOT / 'repack-work/oppo_oplus_realme_sm8850-45405ec4b75ac71c60f3178d1be24db312fae3ff'
p = argparse.ArgumentParser()
p.add_argument('--source', type=Path, default=HERE / 'candidate' / REL)
p.add_argument('--header', type=Path, default=REPO / 'r61-build-route/preimage' / REL.parent / 'inc/bq27z561.h')
p.add_argument('--output', type=Path, default=HERE / 'candidate-tests')
args = p.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
text = args.source.read_text()
header = args.header.read_text()
def extract(signature):
    start = text.index(signature)
    return text[start:text.index('\n}\n', start) + 3]
functions = [extract('static int fg_read_i2c_block_data('),
             extract('static int fg_set_fastcharge_mode('),
             extract('static int fg_set_cutoff_voltage(')]
vendor_enum = re.search(r'enum fg_vendor\s*\{.*?\};', header, re.S).group(0)
mac_constants = []
for name in ['FG_MAC_CMD_CUTOFF_VOLTAGE', 'FG_MAC_CMD_FASTCHARGE_EN', 'FG_MAC_CMD_FASTCHARGE_DIS']:
    value = re.search(r'\b' + name + r'\s*=\s*(0x[0-9a-fA-F]+|[0-9]+)', header).group(1)
    mac_constants.append('#define ' + name + ' ' + value)
limits = [re.search(r'^#define\s+' + name + r'\s+[^\n]+', text, re.M).group(0)
          for name in ['TERM_VOLTAGE_MIN','TERM_VOLTAGE_MAX']]
preamble = r'''
#include <stdio.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#include <stdlib.h>
typedef uint8_t u8;
struct i2c_client { void *adapter; unsigned short addr; };
struct i2c_msg { unsigned short addr, flags, len; u8 *buf; };
struct bq_fg_chip { void *dev; bool fast_mode; int digest_in_process, fg_vendor; };
#define to_i2c_client(d) ((struct i2c_client *)(d))
#define I2C_M_RD 1
#define mca_log_err(...) ((void)0)
#define mca_log_info(...) ((void)0)
#define atomic_read(x) (*(x))
#define CHECK(expr) do { if (!(expr)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#expr); exit(1); } } while (0)
static int transfer_rc, transfer_calls, write_rc, write_calls, last_cmd, last_len;
static u8 last_payload[2];
static int i2c_transfer(void *a, struct i2c_msg *m, int count) {
    CHECK(a != NULL); CHECK(count == 2);
    CHECK(m[0].addr == 0x55 && m[0].flags == 0 && m[0].len == 1 && *m[0].buf == 6);
    CHECK(m[1].addr == 0x55 && m[1].flags == I2C_M_RD && m[1].len == 16);
    transfer_calls++; return transfer_rc;
}
static int fg_mac_write_block(struct bq_fg_chip *b, int cmd, u8 *data, int len) {
    (void)b; CHECK(len == 0 || len == 2);
    write_calls++; last_cmd=cmd; last_len=len;
    if (len == 2) { last_payload[0]=data[0]; last_payload[1]=data[1]; }
    return write_rc;
}
'''
main = r'''
int main(void) {
    unsigned cases=0;
    struct i2c_client client={.adapter=(void *)1,.addr=0x55};
    struct bq_fg_chip b={.dev=&client}; u8 data[16]={0};
    const int returns[]={-EREMOTEIO,-EIO,0,1,2,3};
    for(unsigned i=0;i<sizeof(returns)/sizeof(returns[0]);i++) {
        transfer_rc=returns[i]; transfer_calls=0;
        int rc=fg_read_i2c_block_data(&b,6,16,data);
        CHECK(rc==(transfer_rc<0 ? transfer_rc : transfer_rc==2 ? 2 : -EIO));
        CHECK(transfer_calls==1); cases++;
    }
    transfer_calls=0; CHECK(fg_read_i2c_block_data(&b,6,16,NULL)==-EINVAL); CHECK(!transfer_calls); cases++;
    client.adapter=NULL; CHECK(fg_read_i2c_block_data(&b,6,16,data)==-ENODEV); CHECK(!transfer_calls); cases++;
    b.dev=NULL; CHECK(fg_read_i2c_block_data(&b,6,16,data)==-ENODEV); CHECK(!transfer_calls); cases++;
    b.dev=&client; client.adapter=(void *)1;
    const int values[]={-1,2999,3000,3200,3400,3401,65535};
    for(unsigned i=0;i<sizeof(values)/sizeof(values[0]);i++) {
        write_calls=0; write_rc=0;
        int rc=fg_set_cutoff_voltage(&b,values[i]);
        if(values[i]<3000 || values[i]>3400) { CHECK(rc==-EINVAL); CHECK(!write_calls); }
        else { CHECK(rc==0); CHECK(write_calls==1); CHECK(last_cmd==FG_MAC_CMD_CUTOFF_VOLTAGE);
            CHECK(last_len==2); CHECK((last_payload[0]|(last_payload[1]<<8))==values[i]); }
        cases++;
    }
    write_rc=-EREMOTEIO; write_calls=0;
    CHECK(fg_set_cutoff_voltage(&b,3200)==-EREMOTEIO); CHECK(write_calls==1); cases++;
    for(int vendor=0;vendor<=MPC7021;vendor+=MPC7021) {
        for(int enable=0;enable<=1;enable++) {
            b.fg_vendor=vendor; b.fast_mode=!enable; b.digest_in_process=0; write_calls=0; write_rc=0;
            CHECK(fg_set_fastcharge_mode(&b,enable)==0); CHECK(write_calls==1); CHECK(b.fast_mode==enable);
            CHECK(last_cmd==(enable ? FG_MAC_CMD_FASTCHARGE_EN : FG_MAC_CMD_FASTCHARGE_DIS));
            CHECK(last_len==(vendor==MPC7021 ? 0 : 2));
            if(last_len==2) { CHECK(last_payload[0]==enable); CHECK(last_payload[1]==0); }
            cases++;
        }
    }
    b.fg_vendor=BQ27Z561; b.fast_mode=false; b.digest_in_process=0; write_rc=-EIO; write_calls=0;
    CHECK(fg_set_fastcharge_mode(&b,true)==-EIO); CHECK(write_calls==1); CHECK(!b.fast_mode); cases++;
    b.fast_mode=true; write_calls=0;
    CHECK(fg_set_fastcharge_mode(&b,false)==-EIO); CHECK(write_calls==1); CHECK(b.fast_mode); cases++;
    b.fast_mode=true; write_calls=0;
    CHECK(fg_set_fastcharge_mode(&b,true)==0); CHECK(!write_calls); CHECK(b.fast_mode); cases++;
    b.fast_mode=false; b.digest_in_process=1; write_calls=0; write_rc=0;
    CHECK(fg_set_fastcharge_mode(&b,true)==0); CHECK(!write_calls); CHECK(!b.fast_mode); cases++;
    printf("PASS %u cases: exact production I2C, cutoff and fastcharge helpers; digest-busy unchanged\n",cases);
    return 0;
}
'''
cfile=args.output/'actual-candidate-functions.c'
exe=args.output/'actual-candidate-functions'
cfile.write_text(preamble+'\n'+vendor_enum+'\n'+'\n'.join(mac_constants+limits+functions)+main)
compiler=['cc','-std=c11','-Wall','-Wextra','-Werror','-O1','-ftrivial-auto-var-init=pattern',
          '-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie',str(cfile),'-o',str(exe)]
subprocess.run(compiler,check=True,capture_output=True,text=True)
result=subprocess.run([str(exe)],capture_output=True,text=True,
                      env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0:abort_on_error=1','UBSAN_OPTIONS':'halt_on_error=1'})
(args.output/'RESULTS.txt').write_text(result.stdout+result.stderr)
report={'source':str(args.source),'source_sha256':hashlib.sha256(args.source.read_bytes()).hexdigest(),
        'header':str(args.header),'header_sha256':hashlib.sha256(args.header.read_bytes()).hexdigest(),
        'test_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'compiler_command':compiler,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr,
        'test_scope':'Exact complete helper bodies extracted from source; hardware I/O and kernel plumbing mocked. Source enum/command values extracted from provided real header. ASan and UBSan enabled. No hardware validation.',
        'status':'PASS' if result.returncode==0 else 'FAIL'}
(args.output/'RESULTS.json').write_text(json.dumps(report,indent=2)+'\n')
print(result.stdout,end='')
if result.returncode:
    print(result.stderr,end='')
raise SystemExit(result.returncode)
