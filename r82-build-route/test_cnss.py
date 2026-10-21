#!/usr/bin/env python3
"""Compile the actual pinned CNSS filename function and candidate helpers.

The unchanged function is a separate compiled oracle. Only external boundaries
(hwid values, logging, bus prefix, and the accessed plat fields) are stubbed.
This tests source semantics, not kernel ABI, QMI negotiation or hardware RF.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROUTE = Path(__file__).resolve().parent
TARGET = "cnss_get_bdf_file_name"
HELPERS = ("cnss_is_myron", "cnss_myron_bdf_file_name")
# Filled from the exact independently retrieved f2ecb6a source preimage.
PINNED_QMI_SHA256 = "49da9d95ffab29e1c2c4309f17f181b4ac1b2a7cb11a6c6e8256b7c0588e7533"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def c_mask(source: str) -> str:
    pattern = r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    return re.sub(pattern, lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), source)


def actual_function(source: str, name: str) -> str:
    masked = c_mask(source)
    starts = list(re.finditer(r'(?m)^static\b[^\n]*\b' + re.escape(name) + r'\s*\(', masked))
    if len(starts) != 1:
        raise ValueError(f"Expected one static definition for {name}, found {len(starts)}")
    start = starts[0].start()
    opening = masked.find('{', starts[0].end())
    if opening < 0 or ';' in masked[starts[0].end():opening]:
        raise ValueError(f"Not a function definition: {name}")
    depth = 0
    for pos in range(opening, len(masked)):
        if masked[pos] == '{':
            depth += 1
        elif masked[pos] == '}':
            depth -= 1
            if depth == 0:
                return source[start:pos + 1]
    raise ValueError(f"Unclosed definition: {name}")


def actual_guarded_helpers(source: str) -> str:
    start = source.find('#ifdef MYRON_CNSS_FILE_SELECTION\n')
    if start < 0:
        raise ValueError('Missing actual candidate helper feature guard')
    depth = 0
    for match in re.finditer(r'(?m)^#[ \t]*(if(?:def|ndef)?|endif)\b[^\n]*', source[start:]):
        if match[1] != 'endif':
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                block = source[start:start + match.end()]
                for name in HELPERS:
                    if actual_function(source, name) not in block:
                        raise ValueError('Actual helper escaped its feature guard: ' + name)
                return block
    raise ValueError('Unclosed candidate helper guard')


def actual_macros(source: str) -> str:
    names = r'(?:BDF_FILE_NAME_PREFIX|ELF_BDF_\w+|BIN_BDF_\w+|REGDB_FILE_NAME|HDS_FILE_NAME|CHIP_ID_GF_MASK)'
    lines = re.findall(r'(?m)^#define[ \t]+' + names + r'\b[^\n]*(?:\\\n[^\n]*)*', source)
    if not any('CHIP_ID_GF_MASK' in line for line in lines):
        raise ValueError('Missing actual CHIP_ID_GF_MASK macro')
    return '\n'.join(lines) + '\n'


HEADER = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;
#define PEACH_DEVICE_ID 0x110eU
#define MAX_FIRMWARE_NAME_LEN 40
#define cnss_pr_dbg(...) ((void)0)
#define cnss_pr_info(...) ((void)0)
#define cnss_pr_err(...) ((void)0)
enum cnss_bdf_type { CNSS_BDF_BIN=0, CNSS_BDF_ELF=1,
                     CNSS_BDF_REGDB=4, CNSS_BDF_HDS=6 };
struct cnss_plat_data {
    unsigned long device_id;
    struct { u32 board_id; } board_info;
    struct { u32 chip_id; } chip_info;
    struct { u32 bdf_type; } ctrl_params;
    char bdfname_dt[MAX_FIRMWARE_NAME_LEN];
    unsigned char guard_bytes[16];
};
extern int test_platform, test_country;
extern unsigned prefix_calls;
uint32_t get_hw_version_platform(void);
uint32_t get_hw_country_version(void);
void cnss_bus_add_fw_prefix_name(struct cnss_plat_data *, char *, const char *);
int baseline_run(struct cnss_plat_data *, u32, char *, u32);
int candidate_run(struct cnss_plat_data *, u32, char *, u32);
'''

HARNESS = r'''
#include "test_boundary.h"
#include <limits.h>
#include <stdlib.h>
int test_platform, test_country;
unsigned prefix_calls;
uint32_t get_hw_version_platform(void) { return (uint32_t)test_platform; }
uint32_t get_hw_country_version(void) { return (uint32_t)test_country; }
void cnss_bus_add_fw_prefix_name(struct cnss_plat_data *p, char *out, const char *name)
{
    (void)p;
    ++prefix_calls;
    snprintf(out, 128, "bus-prefix/%s", name);
}
static unsigned long checks, unchanged, allowed_bdf, allowed_regdb, dt_cases;
static void fail(const char *why, const struct cnss_plat_data *p, u32 type,
                 u32 len, const char *got, const char *expected)
{
    fprintf(stderr, "%s: device=%lx platform=%d country=%d board=%x chip=%x type=%u len=%u dt=%s got=%s expected=%s\n",
            why, p->device_id, test_platform, test_country, p->board_info.board_id,
            p->chip_info.chip_id, type, len, p->bdfname_dt, got, expected);
    exit(1);
}
static void run_case(unsigned long device, int platform, int country,
                     u32 board, u32 chip, u32 type, const char *dt, u32 len)
{
    struct cnss_plat_data p, before, b;
    char old_name[128], new_name[128], expected[128], basename[40];
    unsigned old_calls, new_calls;
    memset(&p, 0x5a, sizeof(p));
    p.device_id=device; p.board_info.board_id=board; p.chip_info.chip_id=chip;
    p.ctrl_params.bdf_type=type;
    memset(p.bdfname_dt, 0, sizeof(p.bdfname_dt));
    snprintf(p.bdfname_dt, sizeof(p.bdfname_dt), "%s", dt);
    before=p; b=p;
    test_platform=platform; test_country=country;
    memset(old_name, 0xa5, sizeof(old_name)); strcpy(old_name, "unchanged-output");
    memset(new_name, 0xa5, sizeof(new_name)); strcpy(new_name, "unchanged-output");
    prefix_calls=0;
    int old_ret=baseline_run(&b,type,old_name,len); old_calls=prefix_calls;
    prefix_calls=0;
    int new_ret=candidate_run(&p,type,new_name,len); new_calls=prefix_calls;
    if (memcmp(&before,&p,sizeof(p)) || memcmp(&before,&b,sizeof(b)))
        fail("plat fields mutated",&before,type,len,new_name,old_name);
    if (old_ret!=new_ret || old_calls!=new_calls)
        fail("return/prefix boundary changed",&before,type,len,new_name,old_name);
    const bool myron=TEST_EXPECT_FEATURE && (device==PEACH_DEVICE_ID && platform==4);
    const bool allow_bdf=myron && type==CNSS_BDF_ELF && !dt[0] &&
                         board==0xff && !(chip&0x10);
    const bool allow_regdb=myron && type==CNSS_BDF_REGDB;
    if (allow_bdf || allow_regdb) {
        const char *name;
        if (allow_regdb) { name="regdb_xiaomi.bin"; ++allowed_regdb; }
        else {
            static const char *table[] = {"bd_p11u.elf","bd_p11ugl.elf","bd_p11uin.elf"};
            name=(country>=0 && country<=2) ? table[country] : table[0];
            ++allowed_bdf;
        }
        snprintf(basename,len,"%s",name);
        snprintf(expected,sizeof(expected),"bus-prefix/%s",basename);
        if (new_ret || new_calls!=1 || strcmp(new_name,expected))
            fail("targeted selection",&before,type,len,new_name,expected);
    } else {
        ++unchanged;
        if (memcmp(new_name,old_name,sizeof(old_name)))
            fail("changed outside allowed gate",&before,type,len,new_name,old_name);
    }
    if (type==CNSS_BDF_ELF && dt[0]) {
        ++dt_cases;
        snprintf(basename,len,"%s",dt);
        snprintf(expected,sizeof(expected),"bus-prefix/%s",basename);
        if (strcmp(new_name,expected))
            fail("DT precedence",&before,type,len,new_name,expected);
    }
    if (type!=CNSS_BDF_BIN && type!=CNSS_BDF_ELF &&
        type!=CNSS_BDF_REGDB && type!=CNSS_BDF_HDS) {
        if (new_ret!=-EINVAL || new_calls || strcmp(new_name,"unchanged-output"))
            fail("invalid type side effect",&before,type,len,new_name,"unchanged-output");
    }
    ++checks;
}
int main(void)
{
    const unsigned long devices[]={PEACH_DEVICE_ID,0x110dU,0};
    const int platforms[]={-1,0,1,3,4,5,7,INT_MAX};
    const int countries[]={0,1,2,3,-1};
    const u32 boards[]={0,0xfe,0xff,0x100,0x1234,UINT32_MAX};
    const u32 chips[]={0,0x10,0x11};
    const u32 types[]={0,1,2,4,6,7,UINT32_MAX};
    const char *dts[]={"","from-dt.elf","12345678901234567890123456789012345.elf"};
    const u32 lens[]={1,12,MAX_FIRMWARE_NAME_LEN};
#define EACH(v,a) for (unsigned v=0;v<sizeof(a)/sizeof((a)[0]);++v)
    EACH(a,devices) EACH(b,platforms) EACH(c,countries) EACH(d,boards)
    EACH(e,chips) EACH(f,types) EACH(g,dts) EACH(h,lens)
        run_case(devices[a],platforms[b],countries[c],boards[d],chips[e],types[f],dts[g],lens[h]);
    if ((TEST_EXPECT_FEATURE && (!allowed_bdf || !allowed_regdb)) || !dt_cases || !unchanged) return 2;
    if (!TEST_EXPECT_FEATURE && (allowed_bdf || allowed_regdb || unchanged!=checks)) return 3;
    printf("{\"checks\":%lu,\"unchanged_oracle_cases\":%lu,\"targeted_bdf_cases\":%lu,\"targeted_regdb_cases\":%lu,\"dt_precedence_cases\":%lu}\n",
           checks,unchanged,allowed_bdf,allowed_regdb,dt_cases);
    return 0;
}
'''


def find_candidate(workspace: Path) -> Path:
    direct = [workspace / 'vendor/qcom/sm8850-modules/qcom/opensource/wlan/platform/cnss2/qmi.c',
              workspace / 'qcom/opensource/wlan/platform/cnss2/qmi.c',
              workspace / 'platform/cnss2/qmi.c', workspace / 'qmi.c']
    paths = [p for p in direct if p.is_file()]
    if not paths:
        paths = list(workspace.glob('**/platform/cnss2/qmi.c'))
    if len(paths) != 1:
        raise ValueError(f'Expected one candidate qmi.c in {workspace}, found {paths}')
    return paths[0]


def candidate_from_patch(tmp: Path, original: bytes) -> tuple[Path, str]:
    sections = []
    for patch in sorted(ROUTE.glob('**/*.patch')):
        text = patch.read_text()
        chunks = re.split(r'(?m)(?=^--- a/)', text)
        for chunk in chunks:
            chunk = re.split(r'(?m)^diff --git ', chunk)[0]
            old = re.search(r'(?m)^--- a/(.+/cnss2/qmi\.c)\s*$', chunk)
            new = re.search(r'(?m)^\+\+\+ b/(.+/cnss2/qmi\.c)\s*$', chunk)
            if old and new and old[1] == new[1]:
                sections.append((patch, old[1], chunk))
    if len(sections) != 1:
        raise ValueError(f'Expected exactly one qmi.c patch section, found {len(sections)}')
    patch, relative, chunk = sections[0]
    relative_path = Path(relative)
    if relative_path.is_absolute() or '..' in relative_path.parts:
        raise ValueError('Unsafe patch path')
    source = tmp / relative_path
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(original)
    patch_file = tmp / 'qmi-only.patch'
    patch_file.write_text(chunk)
    result = subprocess.run(['patch', '-p1', '--batch', '--forward', '--fuzz=0', '-i', str(patch_file)],
                            cwd=tmp, text=True, capture_output=True)
    if result.returncode:
        raise ValueError('Pinned qmi patch failed: ' + result.stdout + result.stderr)
    return source, str(patch)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--workspace', type=Path, help='Actual prepared module source workspace')
    ap.add_argument('--report', type=Path, help='Optional JSON evidence output')
    ap.add_argument('--candidate-file', type=Path, help='Explicit prepared qmi.c (development only)')
    ap.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    args = ap.parse_args()
    fixture = ROUTE / 'tests/fixtures/qmi.c'
    original = fixture.read_bytes()
    if sha(original) != PINNED_QMI_SHA256:
        raise ValueError(f'Unexpected pinned original qmi.c hash: {sha(original)}')
    with tempfile.TemporaryDirectory(prefix='r82-cnss-functions-') as directory:
        tmp = Path(directory)
        if args.workspace and args.candidate_file:
            raise ValueError('Choose only one actual source route')
        if args.candidate_file:
            path=args.candidate_file.resolve(); mode='explicit-actual-file'; patch=None
        elif args.workspace:
            path = find_candidate(args.workspace.resolve()); mode='actual-workspace'; patch=None
        else:
            path, patch = candidate_from_patch(tmp/'patched', original); mode='fixture-plus-exact-patch'
        candidate = path.read_bytes()
        baseline_source = original.decode('utf-8'); candidate_source = candidate.decode('utf-8')
        (tmp/'test_boundary.h').write_text(HEADER)
        for variant, source, functions in [('baseline',baseline_source,(TARGET,)),
                                           ('candidate',candidate_source,HELPERS+(TARGET,))]:
            body = ((actual_guarded_helpers(source) + '\n') if variant == 'candidate' else '') + actual_function(source,TARGET)
            unit = '#include "test_boundary.h"\n' + actual_macros(source) + body
            unit += f'\nint {variant}_run(struct cnss_plat_data *p, u32 t, char *f, u32 n) {{ return {TARGET}(p,t,f,n); }}\n'
            (tmp/(variant+'.c')).write_text(unit)
        (tmp/'harness.c').write_text(HARNESS)
        counts = {}
        feature_evidence = {}
        common=[args.cc,'-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined','-fno-omit-frame-pointer']
        for enabled in (True,False):
            label='feature-enabled' if enabled else 'feature-disabled'
            defines=['-DTEST_EXPECT_FEATURE='+str(int(enabled))]
            if enabled:
                defines.append('-DMYRON_CNSS_FILE_SELECTION')
            obj=tmp/(label+'.o')
            result=subprocess.run(common+defines+['-c',str(tmp/'candidate.c'),'-o',str(obj)],text=True,capture_output=True)
            if result.returncode:
                raise RuntimeError('Actual-function host compilation failed:\n'+result.stdout+result.stderr)
            undefined=subprocess.run(['nm','-u',str(obj)],check=True,text=True,capture_output=True).stdout
            getter_imports=sorted(set(re.findall(r'\bget_hw_(?:version_platform|country_version)\b',undefined)))
            if enabled and getter_imports!=['get_hw_country_version','get_hw_version_platform']:
                raise RuntimeError('Enabled helpers not actually compiled: '+undefined)
            if not enabled and getter_imports:
                raise RuntimeError('Disabled target acquired hwid dependencies: '+undefined)
            exe=tmp/label
            command=common+defines+[str(tmp/'baseline.c'),str(obj),str(tmp/'harness.c'),'-o',str(exe)]
            result=subprocess.run(command,text=True,capture_output=True)
            if result.returncode:
                raise RuntimeError('Actual-function harness link failed:\n'+result.stdout+result.stderr)
            env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1')
            result=subprocess.run([str(exe)],text=True,capture_output=True,env=env)
            if result.returncode:
                raise RuntimeError('Actual-function comparison failed:\n'+result.stdout+result.stderr)
            counts[label]=json.loads(result.stdout)
            feature_evidence[label]={'actual_candidate_object_hwid_imports':getter_imports}
        report={'status':'PASS_ACTUAL_CNSS_FUNCTIONS','mode':mode,'candidate':{'path':str(path),'sha256':sha(candidate)},
                'pinned_original_sha256':sha(original),'patch':patch,'actual_candidate_functions':list(HELPERS)+( [TARGET]),
                'checks':counts,'feature_gate':feature_evidence,'compiler':args.cc,'sanitizers':['address','undefined'],
                'scope':'Actual candidate functions compiled against boundary stubs and compared with separately compiled pinned original function outside the permitted filename changes. Targeted basenames checked against independent OEM evidence table. Includes DT precedence, invalid types, truncation at valid lengths 1/12/40, all plat fields unchanged, prefix call/return parity.',
                'limits':['No kernel build/ABI validation or hardware behavior established.','Zero or oversized filename lengths are outside the tested caller contract.','Boundary stubs model accessed fields and hwid return values, not real struct layout or firmware I/O.']}
        if args.report:
            args.report.parent.mkdir(parents=True,exist_ok=True)
            args.report.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))

if __name__ == '__main__':
    main()
