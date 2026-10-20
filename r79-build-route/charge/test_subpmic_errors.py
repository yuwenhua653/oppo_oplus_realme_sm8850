#!/usr/bin/env python3
"""Execute exact production setters with a fault-injected firmware transport.

R76 preimage must fail and R79 postimage must pass. No phone or firmware writes.
Generated C is an extraction of real function bodies, not a Python reimplementation.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
REL = Path('drivers/power/supply/mca/mca_qcom_subpmic_proxy/mca_qcom_subpmic_proxy.c')


def extract(source, name):
    m = re.search(r'^static int ' + re.escape(name) + r'\(', source, re.M)
    if not m:
        raise ValueError('Missing production function: ' + name)
    opening = source.index('{', m.start())
    depth = 0
    for pos in range(opening, len(source)):
        depth += (source[pos] == '{') - (source[pos] == '}')
        if not depth:
            return source[m.start():pos + 1]
    raise ValueError('Unterminated production function')


PRELUDE = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint8_t u8;
#define mca_log_info(...) ((void)0)
static int result, calls, observed_id;
static size_t observed_size;
static unsigned char observed_value[4];
static int mca_adsp_glink_write_prop(int id, const void *value, size_t size)
{
    calls++;
    observed_id = id;
    observed_size = size;
    if (size <= sizeof(observed_value)) memcpy(observed_value, value, size);
    return result;
}
static int check(int actual, int id, const void *value, size_t size, const char *name)
{
    if (actual != result || calls != 1 || observed_id != id ||
        observed_size != size || memcmp(observed_value, value, size)) {
        fprintf(stderr, "FAIL %s ret=%d expected=%d writes=%d id=%#x len=%zu\n",
                name, actual, result, calls, observed_id, observed_size);
        return 1;
    }
    return 0;
}
'''


def run_variant(variant, contract, work):
    path = ROOT / variant / REL
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    expected = contract['preimage_sha256' if variant == 'preimage' else 'postimage_sha256']
    if digest != expected:
        raise ValueError('Source hash mismatch: ' + str(path))
    source = raw.decode()
    enum = re.search(r'^enum mca_subpmic_prop \{.*?^\};', source, re.M | re.S).group(0)
    rows = contract['all_wrappers_tested']
    # Audit every complete function body, not a pattern requiring adjacent lines.
    # Logging or future formatting must not hide a new firmware write owner.
    write_owners = set()
    for match in re.finditer(r'^static (?:int|void) (\w+)\(', source, re.M):
        name = match.group(1)
        opening = source.index('{', match.start())
        depth = 0
        for pos in range(opening, len(source)):
            depth += (source[pos] == '{') - (source[pos] == '}')
            if not depth:
                body = source[match.start():pos + 1]
                break
        if 'mca_adsp_glink_write_prop(' in body:
            write_owners.add(name)
    accounted = ({row['name'] for row in rows} |
                 set(contract['compound_functions_tested']) |
                 set(contract['other_write_owners']))
    if write_owners != accounted:
        raise ValueError('Unclassified firmware write owners: ' + repr(write_owners ^ accounted))
    bodies = '\n'.join(extract(source, row['name']) for row in rows)
    tests = []
    for row in rows:
        typ = 'u8' if row['argument_type'] == 'bool' else 'int'
        value = 'value_index' if typ == 'u8' else '(value_index ? 1500 : 0)'
        tests.append('''
        {
            %(typ)s input = %(value)s;
            calls = 0;
            int actual = %(name)s(NULL, input);
            if (check(actual, %(id)s, &input, sizeof(input), "%(name)s")) return 1;
            checks++;
        }
''' % {'typ': typ, 'value': value, 'name': row['name'], 'id': hex(row['property_id'])})
    main = '''
int main(void) {
    const int results[] = {0, -EIO, -ETIMEDOUT, -ENOTCONN, -ESHUTDOWN, -EOPNOTSUPP, 7};
    int checks = 0;
    if (sizeof(int) != 4 || sizeof(u8) != 1) return 2;
    for (size_t i = 0; i < sizeof(results) / sizeof(results[0]); i++) {
        result = results[i];
        for (int value_index = 0; value_index < 2; value_index++) {
''' + ''.join(tests) + '''
        }
    }
    printf("PASS %d cases: return code, property, wire width, payload and exactly one write\\n", checks);
    return 0;
}
'''
    cfile = work / (variant + '.c')
    cfile.write_text(PRELUDE + enum + bodies + main)
    binary = work / variant
    argv = ['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Wstrict-prototypes',
            '-Werror', '-Wno-unused-parameter', str(cfile), '-o', str(binary)]
    compiled = subprocess.run(argv, text=True, capture_output=True, timeout=30)
    if compiled.returncode:
        raise RuntimeError(compiled.stderr)
    run = subprocess.run([str(binary)], text=True, capture_output=True, timeout=10)
    return {'source_sha256': digest, 'compile_exit_code': compiled.returncode,
            'execution_exit_code': run.returncode, 'stdout': run.stdout.strip(),
            'stderr': run.stderr.strip(), 'function_count': len(rows),
            'function_sha256': {row['name']: hashlib.sha256(extract(source, row['name']).encode()).hexdigest()
                                for row in rows}}


COMPOUND_PRELUDE = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
typedef uint8_t u8;
typedef int64_t s64;
typedef int64_t ktime_t;
#define mca_log_info(...) ((void)0)
#define mca_log_err(...) ((void)0)
/* Values from original mca/protocol/protocol_class.h enum xm_charger_type. */
#define XM_CHARGER_TYPE_HVDCP2 5
#define XM_CHARGER_TYPE_HVDCP3 6
#define XM_CHARGER_TYPE_HVDCP3P5 8
struct qcom_subpmic { int real_type, online; u8 eu_model; };
static int write_rc, read_rc, fail_read_at, reads, writes, sleeps;
static int first_vbus, later_vbus, seen_id, seen_value, failures, checks;
static size_t seen_size;
static ktime_t now;
static ktime_t ktime_get_boottime(void) { return now; }
static s64 ktime_ms_delta(ktime_t end, ktime_t start) { return end - start; }
static void msleep(unsigned int ms) { sleeps++; now += ms; }
static int mca_adsp_glink_read_prop(int id, void *out, size_t size)
{
    reads++;
    if (id != 0x20002 || size != sizeof(int) || reads > 100) abort();
    if (reads == fail_read_at) return read_rc;
    *(int *)out = reads == 1 ? first_vbus : later_vbus;
    return 0;
}
static int mca_adsp_glink_write_prop(int id, const void *in, size_t size)
{
    writes++; seen_id = id; seen_size = size; seen_value = 0;
    if (size > sizeof(seen_value)) abort();
    memcpy(&seen_value, in, size);
    return write_rc;
}
static void reset(void)
{
    write_rc=read_rc=fail_read_at=reads=writes=sleeps=seen_id=seen_value=0;
    seen_size=0; now=0; first_vbus=5000000; later_vbus=9000000;
}
#define EXPECT(condition, label) do { checks++; if (!(condition)) { \
    fprintf(stderr,"FAIL %s reads=%d writes=%d sleeps=%d cache-test\n", \
        label, reads, writes, sleeps); failures++; } } while (0)
'''

COMPOUND_MAIN = r'''
int main(void)
{
    struct qcom_subpmic sc = {XM_CHARGER_TYPE_HVDCP3, 1, 0};
    const int errors[] = {-EIO,-ETIMEDOUT,-ENOTCONN,-ESHUTDOWN,-EOPNOTSUPP,7};
    for (size_t i=0;i<sizeof(errors)/sizeof(errors[0]);i++) {
        int rc;
        reset(); fail_read_at=1; read_rc=errors[i];
        rc=qcom_subpmic_set_qc_volt(&sc,9000);
        EXPECT(rc==errors[i] && reads==1 && writes==0 && sleeps==0,
               "QC initial telemetry failure must stop before firmware write");
        reset(); write_rc=errors[i];
        rc=qcom_subpmic_set_qc_volt(&sc,9000);
        EXPECT(rc==errors[i] && reads==1 && writes==1 && sleeps==0 &&
               seen_id==0x2011 && seen_size==sizeof(int) && seen_value==9000,
               "QC voltage SET failure must propagate without polling");
        reset(); fail_read_at=2; read_rc=errors[i];
        rc=qcom_subpmic_set_qc_volt(&sc,9000);
        EXPECT(rc==errors[i] && reads==2 && writes==1 && sleeps==1,
               "QC settling telemetry failure must propagate without retry writes");
        for (int en=0;en<=1;en++) {
            reset(); write_rc=errors[i]; sc.eu_model=!en;
            rc=qcom_subpmic_set_eu_model(&sc,en);
            EXPECT(rc==errors[i] && sc.eu_model==!en && reads==0 && writes==1 &&
                   seen_id==0x2028 && seen_size==sizeof(u8) && seen_value==en,
                   "EU failed firmware SET must retain last confirmed cache");
        }
    }
    for (int en=0;en<=1;en++) {
        reset(); sc.eu_model=!en;
        int rc=qcom_subpmic_set_eu_model(&sc,en);
        EXPECT(rc==0 && sc.eu_model==en && reads==0 && writes==1 &&
               seen_id==0x2028 && seen_size==sizeof(u8) && seen_value==en,
               "EU successful SET updates cache only after one successful write");
    }
    const int invalid[]={4999,12001,INT_MIN,INT_MAX};
    for (size_t i=0;i<sizeof(invalid)/sizeof(invalid[0]);i++) {
        reset(); int rc=qcom_subpmic_set_qc_volt(&sc,invalid[i]);
        EXPECT(rc==-1 && reads==0 && writes==0 && sleeps==0,
               "QC original voltage bounds reject before any I/O");
    }
    const int types[]={XM_CHARGER_TYPE_HVDCP2,XM_CHARGER_TYPE_HVDCP3,
                       XM_CHARGER_TYPE_HVDCP3P5};
    const int targets[]={5000,9000,12000};
    for (size_t i=0;i<sizeof(types)/sizeof(types[0]);i++) {
        sc.real_type=types[i];
        for (size_t j=0;j<sizeof(targets)/sizeof(targets[0]);j++) {
            reset(); later_vbus=targets[j]*1000;
            int expected_reads=(types[i]==XM_CHARGER_TYPE_HVDCP2||targets[j]==5000)?1:2;
            int rc=qcom_subpmic_set_qc_volt(&sc,targets[j]);
            EXPECT(rc==0 && reads==expected_reads && writes==1 &&
                   seen_id==0x2011 && seen_size==sizeof(int) && seen_value==targets[j],
                   "QC original supported target and type success path unchanged");
        }
        reset(); first_vbus=9000000;
        int rc=qcom_subpmic_set_qc_volt(&sc,9000);
        EXPECT(rc==0 && reads==1 && writes==1 && sleeps==0,
               "QC original already-at-target path does not poll");
    }
    sc.real_type=XM_CHARGER_TYPE_HVDCP3;
    reset(); sc.online=0;
    int rc=qcom_subpmic_set_qc_volt(&sc,9000);
    EXPECT(rc==0 && reads==2 && writes==1 && sleeps==1,
           "QC existing disconnect exit unchanged");
    reset(); sc.online=1; later_vbus=3900000;
    rc=qcom_subpmic_set_qc_volt(&sc,9000);
    EXPECT(rc==0 && reads==2 && writes==1 && sleeps==1,
           "QC existing low bus exit unchanged");
    reset(); later_vbus=5000000;
    rc=qcom_subpmic_set_qc_volt(&sc,9000);
    EXPECT(rc==0 && reads==22 && writes==1 && sleeps==21,
           "QC original bounded settling budget unchanged");
    printf("%s %d compound cases; failures=%d; transport and time are mocks\n",
           failures?"FAIL":"PASS",checks,failures);
    return failures?1:0;
}
'''


def run_compound(variant, contract, work):
    source = (ROOT / variant / REL).read_text()
    enum = re.search(r'^enum mca_subpmic_prop \{.*?^\};', source, re.M | re.S).group(0)
    bounds = '\n'.join(re.findall(r'^#define SUBPMIC_QC_VOLT_(?:MIN|MAX) .*$', source, re.M))
    names = contract['compound_functions_tested']
    bodies = '\n'.join(extract(source, name) for name in names)
    cfile = work / (variant + '-compound.c')
    cfile.write_text(COMPOUND_PRELUDE + enum + '\n' + bounds + '\n' + bodies + COMPOUND_MAIN)
    binary = work / (variant + '-compound')
    argv = ['cc', '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Wstrict-prototypes',
            '-Werror', '-Wno-unused-parameter', '-fsanitize=address,undefined',
            '-fno-omit-frame-pointer', str(cfile), '-o', str(binary)]
    compiled = subprocess.run(argv, text=True, capture_output=True, timeout=30)
    if compiled.returncode:
        raise RuntimeError(compiled.stderr)
    # LeakSanitizer cannot enumerate /proc tasks in this executor. The exact
    # tested functions allocate no memory; address and UB checks remain on.
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0')
    run = subprocess.run([str(binary)], text=True, capture_output=True, timeout=10, env=env)
    return {'compile_exit_code': compiled.returncode, 'execution_exit_code': run.returncode,
            'stdout': run.stdout.strip(), 'stderr': run.stderr.strip(),
            'function_sha256': {name: hashlib.sha256(extract(source, name).encode()).hexdigest()
                                for name in names},
            'sanitizers': ['address', 'undefined'], 'leak_detection': False}


def main():
    contract = json.loads((ROOT / 'PATCH-CONTRACT.json').read_text())
    with tempfile.TemporaryDirectory(prefix='subpmic-tests-', dir=ROOT) as tmp:
        work = Path(tmp)
        before = run_variant('preimage', contract, work)
        after = run_variant('payload', contract, work)
        compound_before = run_compound('preimage', contract, work)
        compound_after = run_compound('payload', contract, work)
    passed = (before['execution_exit_code'] == compound_before['execution_exit_code'] == 1 and
              after['execution_exit_code'] == compound_after['execution_exit_code'] == 0)
    report = {'schema': 1, 'pass': passed, 'preimage_failure_expected': True,
              'preimage': before, 'postimage': after,
              'compound_preimage': compound_before, 'compound_postimage': compound_after,
              'scope': 'Host execution of exact extracted production functions; firmware transport is stubbed.',
              'not_proven': ['Full kernel compilation', 'Firmware policy/response', 'Runtime ABI/CFI',
                             'Original MCA provider closure', 'Real charging power']}
    (ROOT / 'TEST-RESULTS.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['pass', 'preimage_failure_expected']}))
    print('R76:', before['stderr'])
    print('R79:', after['stdout'])
    print('R76 compound:', compound_before['stdout'])
    print('R79 compound:', compound_after['stdout'])
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
