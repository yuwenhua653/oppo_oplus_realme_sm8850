#!/usr/bin/env python3
"""Offline rejection tests and exact-delta checks for the PON-only REC patch."""
import argparse
import copy
import json
import sys
from pathlib import Path

import fix_recovery_keys as fix


def run(source, output, vendor, pair_tools):
    sys.path.insert(0, str(Path(pair_tools).resolve()))
    sys.path.insert(0, str(Path(pair_tools).resolve() / 'image-tools'))
    import read_candidate
    import read_cpio

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

    _, before = read_candidate.read_image(source)
    _, after = read_candidate.read_image(output)
    modules, identities = fix.modules_from_vendor(vendor, read_cpio)
    replacements, plan = fix.make_controls(before, modules)
    additions = {'r97-runtime/modules/' + filename: data for filename, data in modules.items()}
    accept('original_R97_fix1_126_module_verifier', lambda: read_candidate.verify_candidate(source))
    accept('actual_final_image_exact_allowed_delta', lambda: fix.verify_delta(before, after, replacements, additions))
    accept('actual_final_image_empty_early_boot_directories', lambda: read_candidate.check_boot_layout(after))
    accept('PON_dependency_closure_in_load_order', lambda: fix.check_closure(identities, []))
    reject('missing_reboot_mode_dependency', lambda: fix.check_closure(identities[1:], []))
    reject('qcom_pon_before_reboot_mode', lambda: fix.check_closure([identities[1], identities[0], identities[2]], []))
    reject('duplicate_key_module', lambda: fix.check_closure(identities + identities[:1], []))
    reject('truncated_ELF_modinfo', lambda: fix.elf_modinfo(modules['qcom-pon.ko'][:64]))
    damaged = copy.deepcopy(after)
    name = 'r97-runtime/modules/qcom-scm.ko'
    damaged[name]['data'] = bytes([damaged[name]['data'][0] ^ 1]) + damaged[name]['data'][1:]
    reject('tampered_existing_module', lambda: fix.verify_delta(before, damaged, replacements, additions))
    damaged = copy.deepcopy(after)
    name = 'r97-runtime/modules/pm8941-pwrkey.ko'
    damaged[name]['data'] = bytes([damaged[name]['data'][0] ^ 1]) + damaged[name]['data'][1:]
    reject('tampered_new_key_module', lambda: fix.verify_delta(before, damaged, replacements, additions))
    damaged = copy.deepcopy(after)
    damaged['system/etc/init/hw/init.rc']['data'] += b'\n'
    reject('changed_PID1_pinned_RC', lambda: fix.verify_delta(before, damaged, replacements, additions))
    damaged = copy.deepcopy(after)
    damaged['r97-runtime/unexpected'] = dict(damaged['r97-runtime/ui.list'])
    reject('unexpected_runtime_file', lambda: fix.verify_delta(before, damaged, replacements, additions))
    damaged = copy.deepcopy(after)
    damaged['r97-runtime/modules/qcom-pon.ko']['mode'] |= 0o022
    reject('writable_key_module_metadata', lambda: fix.verify_delta(before, damaged, replacements, additions))
    stripped = [r for r in plan['modules'] if r['name'] not in {x[1] for x in fix.KEY_MODULES}]
    fix.need(stripped == json.loads(before['r97-runtime/module-plan.json']['data'])['modules'],
             'retained plan entries/order unchanged')
    tests.append({'name': 'all_126_prior_plan_rows_unchanged_in_order', 'result': 'PASS'})
    return {'status': 'PASS', 'tests': tests, 'count': len(tests), 'device_tested': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for option in ('source', 'output', 'vendor', 'pair-tools'):
        parser.add_argument('--' + option, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.source, args.output, args.vendor, args.pair_tools), indent=2))
