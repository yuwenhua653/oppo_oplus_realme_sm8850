#!/usr/bin/env python3
"""Remove per-module grep processes without removing any REC loading guard.

This assembler accepts only the exact released R97 fix2 image. It changes one
CPIO file, common.sh, and verifies all other records byte for byte. Private
module bytes stay in the local image; this source contains no runtime payload.
"""
import argparse
import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path

SOURCE_SHA = '3781fbdef579681c15127a4a7e40e1ee0fd446387929c0dfaace24c0481446f1'
VENDOR_SHA = '333bdc24a41e2746de9303c15ce9ac86d112fd383587866e82b4c286e09e2cdc'
TARGET = 'r97-runtime/common.sh'
REC_PINS = ('system/bin/init', 'system/bin/recovery', 'system/etc/init/hw/init.rc')
OLD_GUARD = '''loaded_guard() (
    while read -r n size refs deps state rest; do
        [ "$state" = Live ] || fail "non-live $n"
        "$TB" grep -qx "$n" "$BASE/allowed-live.txt" || fail "unexpected module $n"
    done < /proc/modules
)
'''
NEW_GUARD = '''loaded_guard() (
    # Keep every full Live/allowlist check, using shell builtins instead of
    # starting one grep process per loaded module. Module hashes remain checked
    # by preflight. Quoted newline boundaries require a literal complete name.
    newline='
'
    allowed="$newline"
    while IFS= read -r name || [ -n "$name" ]; do
        allowed="$allowed$name$newline"
    done < "$BASE/allowed-live.txt" || fail allowlist
    while read -r n size refs deps state rest; do
        [ "$state" = Live ] || fail "non-live $n"
        case "$allowed" in
            *"$newline$n$newline"*) ;;
            *) fail "unexpected module $n" ;;
        esac
    done < /proc/modules
)
'''


def need(ok, message):
    if not ok:
        raise ValueError(message)


def pin(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def patch_script(data):
    need(data.count(OLD_GUARD.encode()) == 1, 'exact original loaded_guard required')
    result = data.replace(OLD_GUARD.encode(), NEW_GUARD.encode(), 1)
    need(result.replace(NEW_GUARD.encode(), OLD_GUARD.encode(), 1) == data,
         'only loaded_guard changes')
    return result


def verify_delta(before, after, script):
    need(set(before) == set(after), 'unchanged CPIO inventory')
    for name, row in before.items():
        if name == TARGET:
            need(after[name]['data'] == script, 'exact new guard script')
            need({k: v for k, v in row.items() if k != 'data'} ==
                 {k: v for k, v in after[name].items() if k != 'data'}, 'script metadata')
        else:
            need(row == after[name], 'unrelated record changed: ' + name)


def check_modules(entries):
    plan = json.loads(entries['r97-runtime/module-plan.json']['data'])
    need(len(plan['modules']) == 129 and len(plan['firststage']) == 142, 'fix2 module counts')
    need(len(entries['r97-runtime/ui.list']['data'].splitlines()) == 22, '22 UI modules')
    need(len(entries['r97-runtime/hardware.list']['data'].splitlines()) == 57, '57 hardware modules')
    for row in plan['modules']:
        need(pin(entries['r97-runtime/modules/' + row['file']]['data']) ==
             {'bytes': row['bytes'], 'sha256': row['sha256']}, 'module pin: ' + row['file'])
    return plan


def build(source, paired_vendor, out, pair_tools):
    source, out, pair_tools = Path(source), Path(out), Path(pair_tools).resolve()
    sys.path.insert(0, str(pair_tools))
    sys.path.insert(0, str(pair_tools / 'image-tools'))
    candidate = importlib.import_module('read_candidate')
    reader = importlib.import_module('read_cpio')
    im = importlib.import_module('build_images')
    need(not out.exists(), 'output already exists')
    original, before = candidate.read_image(source)
    need(pin(original) == {'bytes': 104857600, 'sha256': SOURCE_SHA}, 'exact released R97 fix2 input')
    paired = Path(paired_vendor).read_bytes()
    need(pin(paired) == {'bytes': 100663296, 'sha256': VENDOR_SHA}, 'exact unchanged paired R97 vendor_boot')
    candidate.check_boot_layout(before)
    check_modules(before)
    script = patch_script(before[TARGET]['data'])
    subprocess.run(['/bin/sh', '-n'], input=script, check=True, capture_output=True)
    codec = im.LegacyLz4()
    header = im.android_header(original, False)
    raw = codec.decompress(original[4096:4096 + header['ramdisk_bytes']])
    cpio, _, _, changes = im.rebuild_cpio(raw, lambda _: False, {TARGET: script}, [])

    def assemble():
        payload, _ = im.recovery_payload(original, codec.compress(cpio, 9))
        return im.append_avb(payload, original, 'recovery', None)

    result, avb = assemble()
    need(result == assemble()[0], 'deterministic image assembly')
    need(len(result) == len(original), 'same 100 MiB recovery partition')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(result)
    _, after = candidate.read_image(out)
    verify_delta(before, after, script)
    candidate.check_boot_layout(after)
    check_modules(after)
    _, old_raw = reader.extract(source)
    _, new_raw = reader.extract(out)
    need(list(old_raw) == list(new_raw), 'unchanged raw CPIO order')
    unchanged = []
    for name, row in old_raw.items():
        if name == TARGET:
            old_fields, new_fields = row['fields'][:], new_raw[name]['fields'][:]
            old_fields[6] = new_fields[6]
            need(old_fields == new_fields, 'all script metadata preserved except data length')
        else:
            need(row['record'] == new_raw[name]['record'], 'unchanged raw CPIO record: ' + name)
            unchanged.append(name)
    final_header = bytearray(result[:4096])
    final_header[12:16] = original[12:16]
    need(final_header == original[:4096], 'header unchanged except ramdisk_size')
    alias = out.parent / 'recovery.img'
    need(not alias.exists(), 'AVB alias already exists')
    alias.hardlink_to(out)
    av = subprocess.run([sys.executable, str(pair_tools / 'image-tools/avbtool.py'),
                         'verify_image', '--image', str(out)], check=True, capture_output=True, text=True)
    report = {
        'status': 'PASS_R97_FIX3_STATIC_NOT_DEVICE_TESTED', 'device_tested': False,
        'source_recovery': pin(original), 'recovery': pin(result), 'vendor_boot': pin(paired),
        'vendor_boot_unchanged': True,
        'recovery_pins_unchanged': {name: pin(after[name]['data']) for name in REC_PINS},
        'module_count_unchanged': 129, 'firststage_unchanged': 142,
        'hardware_list_unchanged': 57, 'ui_list_unchanged': 22,
        'changed_file': TARGET, 'old_script': pin(before[TARGET]['data']), 'new_script': pin(script),
        'unchanged_raw_cpio_records': len(unchanged), 'changed_cpio_records': changes,
        'boot_layout': 'system_dlkm and vendor_dlkm remain empty root-owned directories',
        'all_module_bytes_and_order_unchanged': True, 'all_guard_call_sites_unchanged': True,
        'all_other_runtime_scripts_and_init_rc_unchanged': True,
        'deterministic_assembly': True, 'AVB': avb, 'AVB_verify': av.stdout + av.stderr,
        'latency': 'Device latency must be measured; no fixed seconds guarantee from host tests.',
    }
    out.with_suffix('.review.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for option in ('source', 'paired-vendor', 'out', 'pair-tools'):
        parser.add_argument('--' + option, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.paired_vendor, args.out, args.pair_tools), indent=2))
