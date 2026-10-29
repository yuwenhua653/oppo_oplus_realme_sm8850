#!/usr/bin/env python3
"""Generate a candidate-specific PID1 from the exact R96 native source.

Normal Android /init and all payload/module identity constants remain byte
identical. The Recovery ramdisk /init link is NOT used as a generic-init pin.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
from read_candidate import need, verify_candidate

SOURCE_HASH = '326c784a750db829c1dd89af0190e5f6847bf34d358b9ab8c0c5b3ade2eb00fc'
CONTRACT_HASH = '0fb5767d6013652e879504e0c741b8ca05a4912291ca388b4296b2ae75ad3fd9'

def replace_one(text, old, new):
    need(text.count(old) == 1, 'exact native edit anchor: ' + old[:70])
    return text.replace(old, new, 1)

def generate(baseline, out, reviewed):
    baseline, out = Path(baseline), Path(out)
    original = (baseline / 'r36_init.c').read_bytes()
    contract = (baseline / 'r36_contract.h').read_bytes()
    need(hashlib.sha256(original).hexdigest() == SOURCE_HASH, 'R96 native source pin')
    need(hashlib.sha256(contract).hexdigest() == CONTRACT_HASH, 'R96 normal runtime contract pin')
    pins = reviewed['pins']
    # Size routes only select a pin; they never authenticate a file themselves.
    # Reject the unlikely equal-size ambiguity rather than silently weakening it.
    need(pins['system/bin/recovery']['bytes'] != 4063256, 'R97/legacy Recovery size collision requires explicit review')
    text = original.decode()
    text = replace_one(text, '#include "r36_contract.h"', '#include "r36_contract.h"\n#include "r97_recovery_pins.h"')
    text = replace_one(text, 'static const char recovery_hash[]=', 'static const char *recovery_hash=')
    text = replace_one(text, 'static int recovery_mode,recovery_present,parsed_force=-1;',
        'static int recovery_mode,recovery_present,parsed_force=-1;\nstatic int r97_recovery_selected;')
    at = 'static int select_recovery_rc_size(uint64_t bytes){'
    text = replace_one(text, at, '''static int select_recovery_bundle_size(uint64_t bytes){
 r97_recovery_selected=0;
 recovery_hash="b0d438147ce216b24fe142c4ca3545481051144e00df00a5b2a1538676d7b472";
 if(bytes==4063256)return 0;
 if(bytes==R97_RECOVERY_BYTES){r97_recovery_selected=1;recovery_hash=R97_RECOVERY_SHA256;return 0;}
 return bad();
}
static int select_recovery_rc_size(uint64_t bytes){
 if(r97_recovery_selected){
  if(bytes!=R97_RC_BYTES)return bad();
  recovery_rc_bytes=R97_RC_BYTES;recovery_rc_hash=R97_RC_SHA256;return 0;
 }''')
    text = replace_one(text, 'if(lstat("/system/etc/init/hw/init.rc",&st)||',
                       'if(call.lstat_fn("/system/etc/init/hw/init.rc",&st)||')
    text = replace_one(text, 'static int recovery_rc_copy(struct state*s){', '''static int verify_recovery_bundle(uint64_t bytes){
 if(select_recovery_bundle_size(bytes))return -1;
 if(pin_path("/system/bin/recovery",r97_recovery_selected?R97_RECOVERY_BYTES:4063256,recovery_hash,1))return -1;
 if(r97_recovery_selected&&pin_path("/system/bin/init",R97_INIT_BYTES,R97_INIT_SHA256,1))return -1;
 return select_recovery_rc();
}
static int recovery_rc_copy(struct state*s){''')
    old = 'phase("recovery-detection");if(lstat("/system/bin/recovery",&recovery)==0){recovery_present=1;if(pin_path("/system/bin/recovery",4063256,recovery_hash,1))goto failed;if(select_recovery_rc())goto failed;}else if(errno!=ENOENT&&errno!=ENOTDIR)goto failed;'
    new = '''phase("recovery-detection");if(lstat("/system/bin/recovery",&recovery)==0){
  recovery_present=1;
  if(!S_ISREG(recovery.st_mode)||recovery.st_size<0||verify_recovery_bundle((uint64_t)recovery.st_size))goto failed;
 }else if(errno!=ENOENT&&errno!=ENOTDIR)goto failed;'''
    text = replace_one(text, old, new)
    # In particular, this line and the whole contract must survive verbatim.
    need('phase("generic-init-hash");if(pin_path("/init",R36_INIT_BYTES,R36_INIT_SHA256,1))goto failed;' in text,
         'normal generic init pin changed')
    need(text[text.index(' if(normal_pmsg_setup(&s,1))'): ] ==
         original.decode()[original.decode().index(' if(normal_pmsg_setup(&s,1))'): ], 'normal Android mount/handoff path changed')
    need(not out.exists(), 'output already exists')
    shutil.copytree(baseline, out)
    (out / 'r36_init.c').write_text(text)
    h = ['/* Generated from a verified final R97 Recovery image. */']
    for key, name in [('INIT','system/bin/init'),('RECOVERY','system/bin/recovery'),('RC','system/etc/init/hw/init.rc')]:
        row = pins[name]
        need(isinstance(row['bytes'], int) and 0 < row['bytes'] < 104857600, 'pin size')
        need(len(row['sha256']) == 64 and all(c in '0123456789abcdef' for c in row['sha256']), 'pin hash')
        h.extend([f'#define R97_{key}_BYTES {row["bytes"]}ULL', f'#define R97_{key}_SHA256 "{row["sha256"]}"'])
    (out / 'r97_recovery_pins.h').write_text('\n'.join(h)+'\n')
    need((out / 'r36_contract.h').read_bytes() == contract, 'normal contract changed')
    (out / 'PAIR-PINS.json').write_text(json.dumps(reviewed, indent=2)+'\n')
    return text

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--baseline-native', required=True)
    p.add_argument('--recovery', required=True)
    p.add_argument('--out', required=True)
    a = p.parse_args()
    reviewed = verify_candidate(a.recovery)
    generate(a.baseline_native, a.out, reviewed)
    print(json.dumps(reviewed, indent=2))
