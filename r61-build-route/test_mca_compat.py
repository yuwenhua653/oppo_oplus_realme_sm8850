#!/usr/bin/env python3
"""Host regression of actual MCA log expressions and unsupported FSA paths.

This is not a full ARM64 translation-unit build or hardware validation.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
MCA = ROOT / 'payload/drivers/power/supply/mca'
SHA = lambda value: hashlib.sha256(value).hexdigest()


def statement(source, prefix):
    start = source.index(prefix)
    return source[start:source.index(';', start) + 1]


smart = (MCA / 'mca_smart_charge/mca_smart_charge.c').read_text()
null_log = statement(smart, 'mca_log_err("ops invalid')
vma_log = statement(smart, 'mca_log_err("vma start')
pgtable = (ROOT / 'test-inputs/arm64-pgtable-types.h').read_text()
assert SHA(pgtable.encode()) == '78ec23ab768f06cf2e461f57c92a1d5031e26d3ece5443446839aa4626a76a60'
pg_types = '\n'.join(re.search(pattern, pgtable, re.M).group() for pattern in (
    r'^typedef u64 pteval_t;', r'^typedef struct \{ pteval_t pgprot; \} pgprot_t;',
    r'^#define pgprot_val\(x\)[^\n]+'))
format_prelude = '''
typedef unsigned long long u64;
''' + pg_types + '''
struct vm_area_struct { unsigned long vm_start; pgprot_t vm_page_prot; };
__attribute__((format(printf, 1, 2))) void mca_log_err(const char *, ...);
void check_format(struct vm_area_struct *vma) {
'''

business = (MCA / 'mca_business/business_charger/mca_business_charger.c').read_text()
start = business.index('static int\nbusiness_charger_process_sbu_lpd_status_change(')
helper = business[start:business.index('\nstatic void business_charger_process_event(', start)]
start = business.index('case MCA_EVENT_SBU_LPD_CHANGE: {')
caller = business[start:business.index('\n\t\t\t}', start) + len('\n\t\t\t}')]
fsa_header = (ROOT / 'test-inputs/fsa4480-i2c.h').read_bytes()
fsa_prelude = r'''
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdio.h>
struct device_node { int unused; } node;
struct device { struct device_node *of_node; } dev = { &node };
struct business_charger { struct device *dev; } charger = { &dev };
struct of_phandle_args { struct device_node *np; };
#define IS_ENABLED(x) 1
#define MCA_EVENT_SBU_LPD_CHANGE 7
#include "fsa4480-i2c.h"
static int parse_rc, switch_rc, parse_null;
static int parses, switches, node_puts, logged_errors;
static enum fsa_function last_event;
#define mca_log_err(...) do { ++logged_errors; } while (0)
static int of_parse_phandle_with_args(struct device_node *np, const char *name,
                                     const char *cells, int index,
                                     struct of_phandle_args *args)
{
        (void)name; (void)cells; (void)index;
        assert(np == &node); ++parses;
        args->np = (parse_rc || parse_null) ? NULL : &node;
        return parse_rc;
}
int fsa4480_switch_event(struct device_node *np, enum fsa_function event)
{
        assert(np == &node); ++switches; last_event = event; return switch_rc;
}
static void of_node_put(struct device_node *np) { assert(np == &node); ++node_puts; }
'''
fsa_tests = r'''
static void reset(void) { parse_rc=switch_rc=parse_null=parses=switches=node_puts=logged_errors=0; }
int main(void)
{
        for (int v=1; v<=2; ++v) {
                reset();
                assert(business_charger_process_sbu_lpd_status_change(&charger,v)==-EOPNOTSUPP);
                assert(parses==0 && switches==0 && node_puts==0);
                process_status(&charger,v);
                assert(parses==0 && switches==0 && node_puts==0 && logged_errors==1);
        }
        int values[]={0,3,99,-1};
        for (unsigned i=0; i<sizeof(values)/sizeof(values[0]); ++i) {
                reset();
                assert(business_charger_process_sbu_lpd_status_change(&charger,values[i])==0);
                assert(parses==1 && switches==1 && node_puts==1);
                assert(last_event==FSA_USBC_DISPLAYPORT_DISCONNECTED);
                process_status(&charger,values[i]);
                assert(parses==2 && switches==2 && node_puts==2 && logged_errors==0);
        }
        reset(); parse_rc=-EINVAL;
        assert(business_charger_process_sbu_lpd_status_change(&charger,0)==-EINVAL);
        assert(parses==1 && switches==0 && node_puts==0);
        reset(); parse_null=1;
        assert(business_charger_process_sbu_lpd_status_change(&charger,0)==-ENODEV);
        assert(parses==1 && switches==0 && node_puts==0);
        reset(); switch_rc=-EIO;
        assert(business_charger_process_sbu_lpd_status_change(&charger,0)==-EIO);
        assert(parses==1 && switches==1 && node_puts==1);
        process_status(&charger,0);
        assert(parses==2 && switches==2 && node_puts==2 && logged_errors==1);
        return 0;
}
'''

with tempfile.TemporaryDirectory(prefix='r61-mca-compat-') as directory:
    temp = Path(directory)
    compiler = os.environ.get('CC', 'cc')
    flags = [compiler, '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-Wformat=2']
    source = format_prelude + null_log + '\n' + vma_log + '\n}\n'

    def syntax(text):
        path = temp / 'format.c'
        path.write_text(text)
        return subprocess.run(flags + ['-fsyntax-only', str(path)], text=True, capture_output=True)

    good = syntax(source)
    assert good.returncode == 0, good.stderr
    mutants = {
        'missing_argument': source.replace('ops invalid\\n', 'ops invalid %d\\n'),
        'vm_start_narrow_format': source.replace('vma start 0x%lx', 'vma start 0x%x'),
        'pgprot_struct_argument': source.replace('(unsigned long long)pgprot_val(vma->vm_page_prot)', 'vma->vm_page_prot'),
    }
    for name, text in mutants.items():
        assert text != source and syntax(text).returncode != 0, 'Bad format not rejected: ' + name

    (temp / 'linux').mkdir()
    (temp / 'linux/of.h').write_text('struct device_node;\n')
    (temp / 'linux/notifier.h').write_text('struct notifier_block;\n')
    (temp / 'fsa4480-i2c.h').write_bytes(fsa_header)
    caller_function = ('\nstatic void process_status(struct business_charger *charger, int value) {\n'
                       'struct { void *data; } storage = { &value }, *event_node = &storage;\n'
                       'switch (MCA_EVENT_SBU_LPD_CHANGE) {\n' + caller + '\ndefault: break;\n}\n}\n')
    path = temp / 'fsa.c'
    path.write_text(fsa_prelude + helper + caller_function + fsa_tests)
    result = subprocess.run(flags + ['-I', str(temp), str(path), '-o', str(temp / 'fsa')], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    subprocess.run([str(temp / 'fsa')], check=True)

print(json.dumps({'schema': 1, 'status': 'PASS', 'format_negative_controls': list(mutants),
                  'format_actual_statements_sha256': SHA((null_log + '\n' + vma_log).encode()),
                  'fsa_actual_helper_sha256': SHA(helper.encode()), 'fsa_actual_caller_sha256': SHA(caller.encode()),
                  'fsa_header_sha256': SHA(fsa_header), 'fsa_scenarios': 9,
                  'fsa_unsupported_causes_no_phandle_or_hardware_call': True,
                  'kernel_built': False, 'hardware_tested': False,
                  'scope': 'Actual source fragments; fixed ARM64 pgprot definition and host unsigned-long vm_start type. Full translation-unit and module ABI remain CI checks.'}, indent=2))
