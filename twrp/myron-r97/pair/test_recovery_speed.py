#!/usr/bin/env python3
"""Execute guard behavior on host shells; optionally inspect final image delta.

Without arguments this is a source-only CI test, requiring no private images.
With all three image arguments it also rejects unrelated image modifications.
"""
import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import fix_recovery_speed as fix


def run(source=None, output=None, pair_tools=None):
    tests = []

    def accept(name, operation):
        operation()
        tests.append({'name': name, 'result': 'PASS'})

    def reject(name, operation):
        try:
            operation()
        except (ValueError, AssertionError):
            tests.append({'name': name, 'result': 'PASS_REJECTED'})
            return
        raise AssertionError(name + ': unexpectedly accepted')

    shells = ['/bin/sh']
    for name in ('bash', 'mksh'):
        path = shutil.which(name)
        if path and os.path.realpath(path) not in {os.path.realpath(p) for p in shells}:
            shells.append(path)
    with tempfile.TemporaryDirectory(prefix='r97-guard-test-') as temporary:
        root = Path(temporary)
        allow = root / 'allowed-live.txt'
        proc = root / 'modules'
        count = root / 'grep-count'
        toybox = root / 'toybox'
        toybox.write_text('#!/bin/sh\n[ "$1" = grep ] || exit 99\nshift\nprintf "grep\\n" >> "$COUNT"\nexec /usr/bin/grep "$@"\n')
        toybox.chmod(0o700)

        def execute(shell, body, allowed, names, expected, missing=False, label='', final_newline=True):
            if allow.exists():
                allow.unlink()
            if not missing:
                allow.write_text('\n'.join(allowed) + ('\n' if final_newline and allowed else ''))
            proc.write_text(''.join(f'{n} 4096 0 - {state} 0x0\n' for n, state in names))
            count.write_text('')
            body = body.replace('/proc/modules', '"$PROC"')
            script = 'set -u\nfail() { echo "R97_FAIL $*"; exit 1; }\n' + body + 'loaded_guard\n'
            result = subprocess.run([shell], input=script, text=True, capture_output=True,
                                    env={**os.environ, 'TB': str(toybox), 'BASE': str(root),
                                         'PROC': str(proc), 'COUNT': str(count)}, timeout=15)
            fix.need((result.returncode == 0) == expected,
                     f'{label}: rc {result.returncode}; {result.stdout}; {result.stderr}')
            return count.read_text().count('grep\n')

        allowed = [f'module_{i}' for i in range(221)]
        for shell in shells:
            short = Path(shell).name
            for n in (142, 164, 221):
                names = [(a, 'Live') for a in allowed[:n]]
                old_count = execute(shell, fix.OLD_GUARD, allowed, names, True)
                new_count = execute(shell, fix.NEW_GUARD, allowed, names, True)
                fix.need(old_count == n and new_count == 0, 'no external grep in new guard')
                tests.append({'name': f'{short}_valid_{n}_old_new_agree', 'result': 'PASS',
                              'old_grep_processes': old_count, 'new_grep_processes': new_count})
            for label, rows in (
                ('unknown_first', [('unknown', 'Live')] + [(a, 'Live') for a in allowed]),
                ('unknown_last', [(a, 'Live') for a in allowed] + [('unknown', 'Live')]),
                ('coming_first', [(allowed[0], 'Loading')]),
                ('going_last', [(a, 'Live') for a in allowed[:-1]] + [(allowed[-1], 'Unloading')]),
                ('partial_name', [('module_22_extra', 'Live')]),
                ('suffix_name', [('prefix_module_22', 'Live')]),
                ('substring_name', [('odule_22', 'Live')]),
                ('blank_proc_line', [('', '')]),
            ):
                for version, body in (('old', fix.OLD_GUARD), ('new', fix.NEW_GUARD)):
                    execute(shell, body, allowed, rows, False, label=label)
                tests.append({'name': f'{short}_{label}_both_reject', 'result': 'PASS_REJECTED'})
            for label, values, candidate, expected in (
                ('literal_glob_not_expanded', ['alpha', 'beta'], '*', False),
                ('literal_regex_not_expanded', ['alpha', 'beta'], '.*', False),
                ('no_pipe_boundary_alias', ['alpha', 'beta'], 'alpha|beta', False),
                ('literal_bracket_allowed', ['alpha[1]'], 'alpha[1]', True),
                ('literal_bracket_not_regex', ['alpha[1]'], 'alpha1', False),
                ('literal_question_not_glob', ['alpha'], 'alph?', False),
                ('empty_allowlist', [], 'alpha', False),
                ('literal_pipe_allowed', ['alpha|beta'], 'alpha|beta', True),
                ('literal_star_allowed', ['alpha*'], 'alpha*', True),
                ('duplicate_allowed', ['alpha', 'alpha'], 'alpha', True),
                ('numeric_underscore_name', ['123_alpha'], '123_alpha', True),
            ):
                execute(shell, fix.NEW_GUARD, values, [(candidate, 'Live')], expected, label=label)
                tests.append({'name': f'{short}_{label}', 'result': 'PASS'})
            execute(shell, fix.NEW_GUARD, [], [('alpha', 'Live')], False, missing=True)
            tests.append({'name': f'{short}_missing_allowlist_rejected', 'result': 'PASS_REJECTED'})
            execute(shell, fix.NEW_GUARD, [], [], False, missing=True)
            tests.append({'name': f'{short}_missing_allowlist_empty_proc_rejected', 'result': 'PASS_REJECTED'})
            for body in (fix.OLD_GUARD, fix.NEW_GUARD):
                execute(shell, body, ['alpha'], [('alpha', 'Live')], True, final_newline=False)
                execute(shell, body, ['alpha'], [], True)
            tests.append({'name': f'{short}_unterminated_last_allowlist_line_old_new_agree', 'result': 'PASS'})
            tests.append({'name': f'{short}_empty_proc_old_new_agree', 'result': 'PASS'})
            subprocess.run([shell, '-n'], input=fix.NEW_GUARD.encode(), check=True, capture_output=True)
            tests.append({'name': f'{short}_new_guard_syntax', 'result': 'PASS'})

    reject('unknown_original_guard_rejected', lambda: fix.patch_script(b'loaded_guard() { :; }\n'))
    reject('double_original_guard_rejected', lambda: fix.patch_script((fix.OLD_GUARD * 2).encode()))
    synthetic = ('before\n' + fix.OLD_GUARD + 'preflight\nloaded_guard || fail live_set\nload_list hardware\n').encode()
    new_synthetic = fix.patch_script(synthetic)
    fix.need(new_synthetic.replace(fix.NEW_GUARD.encode(), fix.OLD_GUARD.encode(), 1) == synthetic,
             'all call sites and outside script bytes preserved')
    tests.append({'name': 'all_non_guard_bytes_preserved', 'result': 'PASS'})

    if any((source, output, pair_tools)):
        fix.need(all((source, output, pair_tools)), 'all three image arguments required')
        sys.path.insert(0, str(Path(pair_tools).resolve()))
        import read_candidate
        original, before = read_candidate.read_image(source)
        fix.need(fix.pin(original)['sha256'] == fix.SOURCE_SHA, 'released fix2 source hash')
        _, after = read_candidate.read_image(output)
        script = fix.patch_script(before[fix.TARGET]['data'])
        accept('actual_final_image_exact_one_record_delta', lambda: fix.verify_delta(before, after, script))
        accept('actual_final_image_early_boot_empty_directories', lambda: read_candidate.check_boot_layout(after))
        accept('actual_final_image_all_129_module_hashes', lambda: fix.check_modules(after))
        for label, name in (
            ('tampered_key_module', 'r97-runtime/modules/qcom-pon.ko'),
            ('tampered_mca_module', 'r97-runtime/modules/mca_business_battery_comp.ko'),
            ('changed_hardware_order', 'r97-runtime/hardware.list'),
            ('changed_PID1_pinned_RC', 'system/etc/init/hw/init.rc'),
            ('changed_battery_wait', 'r97-runtime/wait-battery.sh'),
        ):
            fix.need(name in after, 'test file exists: ' + name)
            damaged = copy.deepcopy(after)
            damaged[name]['data'] += b'\n'
            reject(label, lambda: fix.verify_delta(before, damaged, script))
        damaged = copy.deepcopy(after)
        damaged[fix.TARGET]['mode'] |= 0o022
        reject('writable_guard_script_metadata', lambda: fix.verify_delta(before, damaged, script))
        damaged = copy.deepcopy(after)
        damaged['r97-runtime/unexpected'] = dict(damaged[fix.TARGET])
        reject('unexpected_runtime_file', lambda: fix.verify_delta(before, damaged, script))
        damaged = copy.deepcopy(after)
        damaged[fix.TARGET]['data'] = damaged[fix.TARGET]['data'].replace(b'loaded_guard || fail live_set', b': # skipped', 1)
        reject('removed_guard_call', lambda: fix.verify_delta(before, damaged, script))
    return {'status': 'PASS', 'tests': tests, 'count': len(tests), 'host_shells': shells,
            'device_tested': False, 'device_timing_claimed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for option in ('source', 'output', 'pair-tools'):
        parser.add_argument('--' + option)
    args = parser.parse_args()
    print(json.dumps(run(args.source, args.output, args.pair_tools), indent=2))
