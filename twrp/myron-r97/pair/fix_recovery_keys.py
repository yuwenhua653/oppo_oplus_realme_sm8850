#!/usr/bin/env python3
"""Add the exact stable R96 PON key modules to the released R97 fix1 REC.

This local image assembly does not change PID1, Android, TWRP, init RCs,
hardware scripts, or the MCA module set. Private module bytes are read only
from the pinned user-supplied vendor_boot, never from a download or this repo.
"""
import argparse
import copy
import hashlib
import importlib
import json
import stat
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

SOURCE_SHA = 'c40e22fcf52b8c2eb949aa06793d4e8dfcdddd8b0a206f4c5f5c39a13a2441c9'
VENDOR_SHA = '40c62b7f726b011c59149cb9c22ec24a60beafddf4f6ed702506de29ccd03eb3'
PAYLOAD_SHA = '549207605ef4af68d0fac1b7aa4b1c28949a59670c56bdd3c8602e387f6fdfb1'
PAIRED_VENDOR_SHA = '333bdc24a41e2746de9303c15ce9ac86d112fd383587866e82b4c286e09e2cdc'
VERMAGIC = '6.12.81-android16-6-maybe-dirty-4k SMP preempt mod_unload modversions aarch64'
KEY_MODULES = (
    ('reboot-mode.ko', 'reboot_mode', []),
    ('qcom-pon.ko', 'qcom_pon', ['reboot_mode']),
    ('pm8941-pwrkey.ko', 'pm8941_pwrkey', []),
)
CONTROL_NAMES = ('module-plan.json', 'allowed-live.txt', 'modules.sha256', 'ui.list')
REC_PINS = ('system/bin/init', 'system/bin/recovery', 'system/etc/init/hw/init.rc')


def need(ok, message):
    if not ok:
        raise ValueError(message)


def pin(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def elf_modinfo(data):
    """Read .modinfo from bounded, little-endian ELF64 AArch64 module bytes."""
    need(len(data) >= 64 and data[:6] == b'\x7fELF\x02\x01', 'ELF64 LE module')
    need(struct.unpack_from('<HH', data, 16) == (1, 183), 'AArch64 relocatable module')
    offset = struct.unpack_from('<Q', data, 40)[0]
    size, count, names_index = struct.unpack_from('<HHH', data, 58)
    need(size == 64 and 0 < count < 4096 and names_index < count, 'ELF section geometry')
    need(offset + size * count <= len(data), 'ELF section table bounds')
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, offset + i * size) for i in range(count)]

    def contents(row):
        at, length = row[4:6]
        need(at <= len(data) and length <= len(data) - at, 'ELF section bounds')
        return data[at:at + length]

    names = contents(sections[names_index])
    matched = []
    for row in sections:
        at = row[0]
        need(at < len(names) and b'\0' in names[at:], 'ELF section name bounds')
        if names[at:].split(b'\0', 1)[0] == b'.modinfo':
            matched.append(contents(row))
    need(len(matched) == 1, 'one modinfo section')
    result = {}
    for item in matched[0].split(b'\0'):
        if b'=' not in item:
            continue
        key, value = item.decode().split('=', 1)
        if key in ('name', 'depends', 'vermagic'):
            need(key not in result, 'duplicate module identity field')
            result[key] = value
    need(set(result) == {'name', 'depends', 'vermagic'}, 'module identity fields')
    result['depends'] = [x.replace('-', '_') for x in result['depends'].split(',') if x]
    return result


def check_closure(rows, available):
    live = set(available)
    for row in rows:
        need(row['name'] not in live, 'duplicate key module: ' + row['name'])
        need(set(row['depends']) <= live, 'missing dependency: ' + row['name'])
        live.add(row['name'])


def modules_from_vendor(vendor, reader):
    original = Path(vendor).read_bytes()
    need(pin(original) == {'bytes': 100663296, 'sha256': VENDOR_SHA}, 'exact stable R96 vendor_boot')
    _, entries = reader.extract(Path(vendor))
    payload = entries['r32-payload/vendor_dlkm.img']['data']
    need(pin(payload) == {'bytes': 83886080, 'sha256': PAYLOAD_SHA}, 'exact stable vendor module payload')
    result, identities = {}, []
    with tempfile.TemporaryDirectory(prefix='r97-fix2-') as temporary:
        root = Path(temporary)
        image = root / 'vendor_dlkm.img'
        image.write_bytes(payload)
        for filename, name, dependencies in KEY_MODULES:
            output = root / filename
            # No -w: debugfs only reads the pinned ext filesystem.
            subprocess.run(['debugfs', '-R', 'dump /lib/modules/' + filename + ' ' + str(output), str(image)],
                           check=True, capture_output=True, text=True)
            need(output.is_file(), 'module extraction failed: ' + filename)
            data = output.read_bytes()
            identity = elf_modinfo(data)
            need(identity == {'name': name, 'depends': dependencies, 'vermagic': VERMAGIC},
                 'exact module identity: ' + filename)
            result[filename] = data
            identities.append({'file': filename, **identity, **pin(data)})
    check_closure(identities, [])
    return result, identities


def make_controls(before, modules):
    plan = json.loads(before['r97-runtime/module-plan.json']['data'])
    need(len(plan['modules']) == 126 and len(plan['firststage']) == 142, 'original R97 module counts')
    updated = copy.deepcopy(plan)
    insert = next(i for i, row in enumerate(plan['modules']) if row['phase'] == 'hardware')
    additions = []
    for filename, name, _ in KEY_MODULES:
        additions.append({**pin(modules[filename]), 'name': name,
                          'path': '/vendor_dlkm/lib/modules/' + filename,
                          'file': filename, 'firststage': False, 'phase': 'ui', 'args': []})
    updated['modules'][insert:insert] = additions
    need(len({x['name'] for x in updated['modules']}) == 129, 'unique final module names')
    need(len({x['file'] for x in updated['modules']}) == 129, 'unique final module files')
    need(not ({x['name'] for x in additions} & set(plan['firststage'])), 'keys already in firststage')
    controls = {
        'module-plan.json': json.dumps(updated, indent=2) + '\n',
        'allowed-live.txt': '\n'.join(sorted(set(updated['firststage']) | {r['name'] for r in updated['modules']})) + '\n',
        'modules.sha256': ''.join(r['sha256'] + '  modules/' + r['file'] + '\n' for r in updated['modules']),
        'ui.list': ''.join('|'.join([r['name'], r['file'], ' '.join(r['args'])]) + '\n'
                           for r in updated['modules'] if r['phase'] == 'ui' and not r['firststage']),
    }
    need(len(controls['ui.list'].splitlines()) == 22, '22 new UI modules including three key modules')
    need(len(before['r97-runtime/hardware.list']['data'].splitlines()) == 57, '57 hardware modules')
    return {'r97-runtime/' + n: b.encode() for n, b in controls.items()}, updated


def verify_delta(before, after, replacements, additions):
    need(set(after) == set(before) | set(additions), 'exact final CPIO inventory')
    for name, row in before.items():
        if name in replacements:
            need(after[name]['data'] == replacements[name], 'final control bytes: ' + name)
            need({k: v for k, v in row.items() if k != 'data'} ==
                 {k: v for k, v in after[name].items() if k != 'data'}, 'control metadata: ' + name)
        else:
            need(after[name] == row, 'unrelated record changed: ' + name)
    for name, data in additions.items():
        need(after[name] == {'mode': stat.S_IFREG | 0o644, 'uid': 0, 'gid': 0, 'data': data},
             'added key module bytes/metadata: ' + name)


def build(source, vendor, paired_vendor, out, pair_tools):
    source, out, pair_tools = Path(source), Path(out), Path(pair_tools).resolve()
    sys.path.insert(0, str(pair_tools))
    sys.path.insert(0, str(pair_tools / 'image-tools'))
    candidate = importlib.import_module('read_candidate')
    reader = importlib.import_module('read_cpio')
    im = importlib.import_module('build_images')
    need(not out.exists(), 'output already exists')
    original, before = candidate.read_image(source)
    need(pin(original) == {'bytes': 104857600, 'sha256': SOURCE_SHA}, 'exact released R97 fix1 input')
    reviewed = candidate.verify_candidate(source)  # checks all 126 prior module and overlay hashes
    paired = Path(paired_vendor).read_bytes()
    need(pin(paired) == {'bytes': 100663296, 'sha256': PAIRED_VENDOR_SHA}, 'exact unchanged R97 paired vendor_boot')
    modules, identities = modules_from_vendor(vendor, reader)
    replacements, plan = make_controls(before, modules)
    additions = {'r97-runtime/modules/' + filename: data for filename, data in modules.items()}
    codec = im.LegacyLz4()
    header = im.android_header(original, False)
    raw = codec.decompress(original[4096:4096 + header['ramdisk_bytes']])
    cpio, _, _, changes = im.rebuild_cpio(raw, lambda _: False, replacements,
                                         [(name, data, 0o100644) for name, data in additions.items()])

    def assemble():
        payload, _ = im.recovery_payload(original, codec.compress(cpio, 9))
        return im.append_avb(payload, original, 'recovery', None)

    result, avb = assemble()
    need(result == assemble()[0], 'deterministic image assembly')
    need(len(result) == len(original), 'same 100 MiB recovery partition')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(result)
    _, after = candidate.read_image(out)
    verify_delta(before, after, replacements, additions)
    candidate.check_boot_layout(after)
    _, old_raw = reader.extract(source)
    _, new_raw = reader.extract(out)
    need(list(new_raw) == list(old_raw)[:-1] + list(additions) + ['TRAILER!!!'], 'preserved raw CPIO order')
    unchanged = []
    for name, row in old_raw.items():
        if name in replacements:
            old_fields, new_fields = row['fields'][:], new_raw[name]['fields'][:]
            old_fields[6] = new_fields[6]
            need(old_fields == new_fields, 'all control CPIO metadata preserved: ' + name)
        else:
            need(row['record'] == new_raw[name]['record'], 'unchanged raw CPIO record: ' + name)
            unchanged.append(name)
    for name in REC_PINS:
        need(before[name] == after[name], 'existing PID1 pin preserved: ' + name)
    final_header = bytearray(result[:4096])
    final_header[12:16] = original[12:16]
    need(final_header == original[:4096], 'header unchanged except ramdisk_size')
    for row in plan['modules']:
        need(pin(after['r97-runtime/modules/' + row['file']]['data']) ==
             {'bytes': row['bytes'], 'sha256': row['sha256']}, 'final module pin: ' + row['file'])
    alias = out.parent / 'recovery.img'
    need(not alias.exists(), 'AVB alias already exists')
    alias.hardlink_to(out)
    av = subprocess.run([sys.executable, str(pair_tools / 'image-tools/avbtool.py'),
                         'verify_image', '--image', str(out)], check=True, capture_output=True, text=True)
    report = {
        'status': 'PASS_R97_FIX2_STATIC_NOT_DEVICE_TESTED', 'device_tested': False,
        'source_recovery': pin(original), 'recovery': pin(result), 'vendor_boot': pin(paired),
        'vendor_boot_unchanged': True, 'recovery_pins_unchanged': reviewed['pins'],
        'original_module_count': 126, 'final_module_count': 129,
        'firststage_unchanged': 142, 'hardware_list_unchanged': 57, 'ui_list_count': 22,
        'added_key_modules': identities, 'changed_controls': list(replacements),
        'new_module_plan': pin(replacements['r97-runtime/module-plan.json']),
        'unchanged_raw_cpio_records': len(unchanged), 'changed_cpio_records': changes,
        'boot_layout': 'system_dlkm and vendor_dlkm remain empty root-owned directories',
        'all_existing_runtime_scripts_unchanged': True, 'all_existing_modules_unchanged': True,
        'deterministic_assembly': True, 'AVB': avb, 'AVB_verify': av.stdout + av.stderr,
    }
    out.with_suffix('.review.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for option in ('source', 'vendor', 'paired-vendor', 'out', 'pair-tools'):
        parser.add_argument('--' + option, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.vendor, args.paired_vendor, args.out, args.pair_tools), indent=2))
