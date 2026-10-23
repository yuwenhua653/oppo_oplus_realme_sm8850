#!/usr/bin/env python3
"""Execute exact FG initialization and policy functions with provider fault injection."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
sys.dont_write_bytecode = True
from extract import function

HERE = Path(__file__).resolve().parent
OLD_SMOOTH_SHA = '141889a0c5470421c51317873913383f21fa0f469934d1d945af5eae4691be8d'
NAMES = ['strategy_fg_require_optional_op', 'strategy_fg_check_optional_ops',
         'strategy_fg_read_eu_policy', 'mca_strategy_check_recharge',
         'mca_strategy_check_lossless_recharge', 'strategy_fg_ops_get_soc_decimal',
         'strategy_fg_ops_set_charging_done', 'strategy_fg_process_event',
         'strategy_fg_update_qbg_chg_data', 'strategy_fg_probe']
SMOOTH = ['get_unit_time_low_soc', 'fg_update_mapped_soc',
          'fg_ui_soc_process_special_conditions', 'fg_ui_soc_update_decimal',
          'fg_ui_soc_smooth']
CONSTANTS = ['STRATEGY_FG_UPDATE_PERIOD_NONE', 'STRATEGY_FG_WORK_INTERVAL_FAST',
             'STRATEGY_FG_WORK_INTERVAL_DTPT', 'STRATEGY_FG_ABNORMAL_DFX_DELAY',
             'NVT1000_OTA_MONITOR_INTERVAL', 'NVT1000_OTA_UPDATE_FLAG',
             'EU_RECHARGER_SOC', 'EU_LOSSES_START_CYCLECOUNT', 'EU_MODEL_RECHARGE_SOC',
             'STRATEGY_FG_SOC_DECIMAL_DEFAULT_RATE', 'QBG_CHG_DATA_DEFAULT_IBAT_MAX',
             'QBG_CHG_DATA_DEFAULT_TERM_CURR', 'QBG_CHG_DATA_DEFAULT_TERM_VOLT']

def pin(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

def build(source, header, smooth, out, candidate):
    text, htext, stext = source.read_text(), header.read_text(), smooth.read_text()
    bodies = {name: function(text, name) for name in NAMES
              if candidate or name != 'strategy_fg_read_eu_policy'}
    sbodies = {name: function(stext, name) for name in SMOOTH}
    constants = []
    for name in CONSTANTS:
        match = re.search(r'^#define\s+' + name + r'\s+.*$', text, re.M)
        assert match, name
        constants.append(match.group())
    for name in ['EU_SOC_PROPORTION_C', 'EU_SOC_PROPORTION']:
        constants.append(re.search(r'^#define\s+' + name + r'\s+.*$', stext, re.M).group())
    threshold = (HERE / 'mca_soc_smooth.h').read_bytes()
    assert pin(threshold)['sha256'] == 'efa6c2ba00d7cc0816e250e2ce920684c638e8577676d3dd8d3edd9fafd05874'
    constants.append(re.search(r'^#define\s+FG_HOLD_UISOC_100_GAP\s+.*$', threshold.decode(), re.M).group().rstrip())
    # Only external includes are removed; all actual private enum/struct definitions stay intact.
    htext = re.sub(r'^#include[^\n]*\n', '', htext, flags=re.M)
    generated = '\n'.join([
        '#define CANDIDATE ' + str(int(candidate)),
        (HERE / 'host_pre.h').read_text(), htext, '\n'.join(constants),
        (HERE / 'host_post.h').read_text(),
        '\n\n'.join(bodies.values()), '\n\n'.join(sbodies.values()),
        (HERE / 'cases.c').read_text(),
    ])
    out.mkdir(parents=True, exist_ok=False)
    cfile = out / 'production.c'
    cfile.write_text(generated)
    command = ['cc', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-sign-compare',
               '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-no-pie',
               str(cfile), '-o', str(out / 'tests')]
    result = subprocess.run(command, capture_output=True, text=True)
    (out / 'build.log').write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stderr
    return {'source': pin(source.read_bytes()), 'header': pin(header.read_bytes()),
            'soc_smooth': pin(smooth.read_bytes()), 'compiler': command,
            'unmodified_functions': {name: pin(body.encode()) for name, body in {**bodies, **sbodies}.items()},
            'production_constants': constants}

def run(exe, *arguments):
    return subprocess.run([str(exe), *arguments], capture_output=True, text=True, timeout=30,
                          env={**os.environ, 'ASAN_OPTIONS': 'detect_leaks=0:abort_on_error=1',
                               'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'})

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['source', 'header', 'soc-smooth', 'before', 'before-soc-smooth', 'out']:
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    assert not a.out.exists(), 'Fresh output required'
    assert pin(a.before_soc_smooth.read_bytes())['sha256'] == OLD_SMOOTH_SHA, 'Exact compiled R87 smooth required'
    # The old source pin is populated from the frozen reviewed snapshot, never inferred from after-source.
    expected = json.loads((HERE / 'PROVENANCE.json').read_text())
    assert pin(a.before.read_bytes()) == expected['r87_strategy'], 'Exact compiled R87 FG required'
    before_header = a.before.parent / 'inc/strategy_fg.h'
    assert pin(before_header.read_bytes()) == expected['r87_strategy_header'], 'Exact compiled R87 private header required'
    candidate = build(a.source, a.header, a.soc_smooth, a.out / 'candidate', True)
    result = run(a.out / 'candidate/tests')
    (a.out / 'candidate/run.log').write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    original = build(a.before, before_header, a.before_soc_smooth,
                     a.out / 'original', False)
    negatives = {
        'probe_storage': 'result==0',
        'optional_missing': 'result==0',
        'dt_errno': 'result==-EINVAL',
        'unknown_map': 'fg.batt_mapped_soc==37',
        'unknown_recharge': 'recharge_count==0',
        'unknown_lossless': 'recharge_count==0',
        'unknown_done': '!fg.keep_full_flag',
        'invalid_event': 'result==-EINVAL',
        'late_false_event': '!fg.is_eu_model',
        'unknown_hold': 'result==99',
        'unknown_decimal': 'fg.batt_ui_soc_decimal==0',
    }
    proofs = {}
    for case, assertion in negatives.items():
        old = run(a.out / 'original/tests', case)
        (a.out / 'original' / (case + '.log')).write_text(old.stdout + old.stderr)
        assert old.returncode == 41 and ('FAIL ' + case + ': ' + assertion) in old.stderr, case + ': ' + old.stderr
        assert 'ERROR: AddressSanitizer' not in old.stderr and 'runtime error:' not in old.stderr
        proofs[case] = {'status': 'FAILS_EXACT_R87', 'assertion': assertion}
    report = {'schema': 1, 'status': 'PASS_ACTUAL_FG_OPTIONAL_POLICY_FAULT_MATRIX',
              'candidate': candidate, 'before': original, 'original_negative_proofs': proofs,
              'output': result.stdout.strip(), 'ASan_UBSan_Werror': True,
              'target_compiled': False, 'hardware_tested': False,
              'limitations': 'Exact selected production C functions, actual private FG header and pinned original SOC smoothing constants; kernel allocation, registration, voters, scheduler, clocks and providers are stubbed. -Wno-sign-compare permits the inherited signed int comparison with unsigned OTA magic 0xAA55AA55. Does not execute the complete kernel module lifetime or real battery transport.'}
    (a.out / 'RESULT.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(result.stdout.strip())
    print('PASS eleven exact R87 negative controls; ASan/UBSan/Werror')

if __name__ == '__main__':
    main()
