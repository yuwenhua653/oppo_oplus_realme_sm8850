#!/usr/bin/env python3
"""Exercise exact USB power-supply callbacks with provider fault injection."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

PRELUDE = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
enum power_supply_property { POWER_SUPPLY_PROP_PRESENT, POWER_SUPPLY_PROP_ONLINE,
 POWER_SUPPLY_PROP_VOLTAGE_MAX, POWER_SUPPLY_PROP_VOLTAGE_NOW,
 POWER_SUPPLY_PROP_CURRENT_NOW, POWER_SUPPLY_PROP_CURRENT_MAX,
 POWER_SUPPLY_PROP_TYPE, POWER_SUPPLY_PROP_INPUT_CURRENT_LIMIT };
union power_supply_propval { int intval; };
struct power_supply_desc { int type; };
struct usb_psy_info { int present, online; };
struct power_supply { struct usb_psy_info *data; const struct power_supply_desc *desc; };
static void *power_supply_get_drvdata(struct power_supply *p) { return p->data; }
#define STRATEGY_FUNC_TYPE_BUCK_CHARGE 17
#define STRATEGY_STATUS_TYPE_ONLINE 19
#define STRATEGY_CONFIG_INPUT_CURRENT_LIMIT 23
#define MAIN_BUCK_CHARGER 29
#define mca_log_err(...) ((void)0)
static int provider_rc, provider_value, provider_calls, setter_calls, setter_value;
static int read_provider(int *v) { ++provider_calls; *v=provider_value; return provider_rc; }
static int mca_strategy_func_get_status(int a,int b,int *v) {
 assert(a==17 && b==19); return read_provider(v);
}
static int platform_class_buckchg_ops_get_usb_sns_volt(int a,int *v) {
 assert(a==29); return read_provider(v);
}
static int platform_class_buckchg_ops_get_bus_volt(int a,int *v) {
 assert(a==29); return read_provider(v);
}
static int platform_class_buckchg_ops_get_bus_curr(int a,int *v) {
 assert(a==29); return read_provider(v);
}
static int mca_strategy_func_set_config(int a,int b,int v) {
 assert(a==17 && b==23); ++setter_calls; setter_value=v; return provider_rc;
}
'''

TESTS = r'''
int main(void) {
 struct usb_psy_info info={.present=1,.online=1};
 const struct power_supply_desc desc={.type=41};
 struct power_supply psy={.data=&info,.desc=&desc};
 union power_supply_propval val;
 enum power_supply_property reads[]={POWER_SUPPLY_PROP_PRESENT,POWER_SUPPLY_PROP_ONLINE,
  POWER_SUPPLY_PROP_VOLTAGE_MAX,POWER_SUPPLY_PROP_VOLTAGE_NOW,POWER_SUPPLY_PROP_CURRENT_NOW};
 int errors[]={-EIO,-ETIMEDOUT,-ENODEV};
 int cases=0;
 for(unsigned i=0;i<sizeof(reads)/sizeof(reads[0]);i++) {
  provider_calls=0; provider_rc=0; provider_value=i<2 ? 1:4861000;
  val.intval=0x123456;
  assert(usb_psy_get_prop(&psy,reads[i],&val)==0);
  assert(val.intval==provider_value && provider_calls==1); ++cases;
  for(unsigned j=0;j<sizeof(errors)/sizeof(errors[0]);j++) {
   provider_calls=0; provider_rc=errors[j]; provider_value=-987654;
   val.intval=0x123456; info.present=info.online=1;
   assert(usb_psy_get_prop(&psy,reads[i],&val)==-ENODATA);
   assert(val.intval==0x123456 && provider_calls==1);
   assert(info.present==1 && info.online==1); ++cases;
  }
 }
 provider_rc=0; provider_value=0; val.intval=9;
 assert(usb_psy_get_prop(&psy,POWER_SUPPLY_PROP_ONLINE,&val)==0);
 assert(val.intval==0 && info.online==0); ++cases;
 provider_calls=0; val.intval=9;
 assert(usb_psy_get_prop(&psy,POWER_SUPPLY_PROP_TYPE,&val)==0);
 assert(val.intval==41 && provider_calls==0); ++cases;
 enum power_supply_property unsupported[]={POWER_SUPPLY_PROP_CURRENT_MAX,
  POWER_SUPPLY_PROP_INPUT_CURRENT_LIMIT,(enum power_supply_property)999};
 for(unsigned i=0;i<sizeof(unsupported)/sizeof(unsupported[0]);i++) {
  val.intval=0x123456; provider_calls=0;
  assert(usb_psy_get_prop(&psy,unsupported[i],&val)==-ENODATA);
  assert(val.intval==0x123456 && provider_calls==0); ++cases;
 }
 val.intval=500000; provider_rc=0; setter_calls=0;
 assert(usb_psy_set_prop(&psy,POWER_SUPPLY_PROP_INPUT_CURRENT_LIMIT,&val)==0);
 assert(setter_calls==1 && setter_value==500000); ++cases;
 for(unsigned i=0;i<sizeof(errors)/sizeof(errors[0]);i++) {
  setter_calls=0; provider_rc=errors[i];
  assert(usb_psy_set_prop(&psy,POWER_SUPPLY_PROP_INPUT_CURRENT_LIMIT,&val)==-ENODATA);
  assert(setter_calls==1 && setter_value==500000); ++cases;
 }
 setter_calls=0;
 assert(usb_psy_set_prop(&psy,POWER_SUPPLY_PROP_ONLINE,&val)==-ENODATA);
 assert(setter_calls==0); ++cases;
 for(int i=0;i<=POWER_SUPPLY_PROP_INPUT_CURRENT_LIMIT;i++) {
  assert(usb_psy_prop_is_writeable(&psy,i)==(i==POWER_SUPPLY_PROP_INPUT_CURRENT_LIMIT));
 }
 ++cases;
 printf("PASS %d contract cases; actual production get/set/writeability bodies\n",cases);
 return 0;
}
'''


def body(source, name):
    marker = 'static int ' + name + '('
    start = source.index(marker)
    opening = source.index('{', start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == '{':
            depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise ValueError('Unterminated production function ' + name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--expect-failure', action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    data = args.source.read_bytes()
    functions = [body(data.decode(), n) for n in ('usb_psy_get_prop', 'usb_psy_set_prop', 'usb_psy_prop_is_writeable')]
    c = args.out / 'actual-functions.c'
    c.write_text(PRELUDE + '\n\n'.join(functions) + TESTS)
    binary = args.out / 'actual-functions'
    command = ['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-O1',
               '-ftrivial-auto-var-init=pattern', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
               '-no-pie', str(c), '-o', str(binary)]
    compiled = subprocess.run(command, capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    result = subprocess.run([str(binary)], capture_output=True, text=True,
                            env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0:abort_on_error=1',
                                 'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'})
    assert (result.returncode != 0) if args.expect_failure else (result.returncode == 0), result.stderr
    report = {'source_sha256': hashlib.sha256(data).hexdigest(), 'function_sha256': {
        name: hashlib.sha256(code.encode()).hexdigest() for name, code in zip(
            ('usb_psy_get_prop', 'usb_psy_set_prop', 'usb_psy_prop_is_writeable'), functions)},
        'compile_command': command, 'exit_code': result.returncode, 'stdout': result.stdout,
        'stderr': result.stderr, 'expected_original_failure': args.expect_failure,
        'status': 'PASS_NEGATIVE_PROOF' if args.expect_failure else 'PASS',
        'limitation': 'Exact production function bodies, mocked provider/kernel types; actual target compile and runtime qualification separate.'}
    (args.out / 'RESULT.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('status', 'source_sha256', 'stdout')}))


if __name__ == '__main__':
    main()
