#!/usr/bin/env python3
"""Read an Android boot v4 recovery candidate without extracting paths.

This verifier reads the final image, not the build output directory. It never
writes partitions, accepts a kernel, or invents module bytes.
"""
import ctypes
import ctypes.util
import hashlib
import json
import stat
import struct
from pathlib import Path

MODULE_PLAN_SHA256 = 'e76c873b4d51298c9ea2cb219455c47bfe06fb061613800783ad5f1afae03331'
RUNTIME_ID = 'R94-MCA-TORCH-COMPAT-20261028-01'

def need(value, message):
    if not value:
        raise ValueError(message)

def pin(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

def align(n, a=4096):
    return (n + a - 1) // a * a

def legacy_lz4(data):
    need(data[:4] == b'\x02\x21\x4c\x18', 'legacy LZ4 ramdisk required')
    lib = ctypes.CDLL(ctypes.util.find_library('lz4') or 'liblz4.so.1')
    lib.LZ4_decompress_safe.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    lib.LZ4_decompress_safe.restype = ctypes.c_int
    result = bytearray()
    at = 4
    while at < len(data):
        need(at + 4 <= len(data), 'truncated LZ4 length')
        size, = struct.unpack_from('<I', data, at)
        at += 4
        need(0 < size <= 9 * 1024 * 1024 and at + size <= len(data), 'bad LZ4 block')
        source = ctypes.create_string_buffer(data[at:at + size])
        target = ctypes.create_string_buffer(8 * 1024 * 1024)
        n = lib.LZ4_decompress_safe(source, target, size, len(target))
        need(n > 0, 'LZ4 decode failed')
        result.extend(target.raw[:n])
        need(len(result) <= 512 * 1024 * 1024, 'oversized ramdisk')
        at += size
    return bytes(result)

def newc(data):
    entries = {}
    at = 0
    while True:
        need(at + 110 <= len(data), 'truncated CPIO header')
        h = data[at:at + 110]
        need(h[:6] == b'070701', 'newc CPIO required')
        values = [int(h[6 + i * 8:14 + i * 8], 16) for i in range(13)]
        mode, size, namesize = values[1], values[6], values[11]
        at += 110
        need(1 < namesize <= 4096 and at + namesize <= len(data), 'bad CPIO name')
        name_bytes = data[at:at + namesize]
        need(name_bytes[-1:] == b'\0' and b'\0' not in name_bytes[:-1], 'bad CPIO terminator')
        name = name_bytes[:-1].decode('utf-8')
        at = align(at + namesize, 4)
        need(at + size <= len(data), 'truncated CPIO data')
        content = data[at:at + size]
        at = align(at + size, 4)
        if name == 'TRAILER!!!':
            need(size == 0 and not any(data[at:]), 'nonempty CPIO trailer')
            return entries
        if name.startswith('./'):
            name = name[2:]
        need(name not in entries and not name.startswith('/') and '..' not in name.split('/'), 'unsafe or duplicate CPIO name')
        entries[name] = {'mode': mode, 'uid':values[2], 'gid':values[3], 'data': content}

def read_image(path):
    image = Path(path).read_bytes()
    need(len(image) <= 104857600 and len(image) >= 8192, 'recovery partition geometry')
    need(image[:8] == b'ANDROID!', 'Android boot magic')
    kernel, ramdisk, _, header = struct.unpack_from('<4I', image, 8)
    version, = struct.unpack_from('<I', image, 40)
    need(version == 4 and header == 1584 and kernel == 0, 'kernel-less boot v4 recovery required')
    need(ramdisk > 0 and 4096 + ramdisk <= len(image), 'ramdisk geometry')
    return image, newc(legacy_lz4(image[4096:4096 + ramdisk]))

def regular(entries, path, executable=False):
    need(path in entries, 'missing ' + path)
    item = entries[path]
    need(stat.S_ISREG(item['mode']), 'regular file required: ' + path)
    need(item['uid']==0 and item['gid']==0 and not (item['mode'] & 0o022),'root-owned non-writable input required: '+path)
    if executable:
        need(item['mode'] & 0o111, 'executable required: ' + path)
    return item['data']

def verify_candidate(path):
    image, entries = read_image(path)
    return verify_entries(entries, pin(image))

def check_boot_layout(entries, allow_known_vendor_link=False):
    """Match PID1's pre-mode empty_dir contract without weakening PID1."""
    remove = set()
    for name in ['system_dlkm', 'vendor_dlkm']:
        need(name in entries, 'missing early boot directory: '+name)
        row = entries[name]
        need(stat.S_ISDIR(row['mode']) and row['uid']==row['gid']==0 and
             not (row['mode'] & 0o022), 'early boot directory metadata: '+name)
        children = {n for n in entries if n.startswith(name+'/')}
        if allow_known_vendor_link and name=='vendor_dlkm' and children=={'vendor_dlkm/etc'}:
            link=entries['vendor_dlkm/etc']
            need(stat.S_ISLNK(link['mode']) and link['uid']==link['gid']==0 and
                 link['data']==b'/vendor/vendor_dlkm/etc', 'unexpected vendor_dlkm/etc input')
            remove.add('vendor_dlkm/etc')
        else:
            need(not children, 'PID1 early boot directory-not-empty: '+name)
    return remove

def verify_entries(entries, image_pin):
    check_boot_layout(entries)
    need('R97-COMPILE-ONLY-NOT-FLASHABLE' not in entries, 'source-only compile candidate cannot be paired')
    need('init' in entries and stat.S_ISLNK(entries['init']['mode']) and
         entries['init']['data'] == b'/system/bin/init', 'original recovery /init link layout required')
    pins = {name: pin(regular(entries, name, name != 'system/etc/init/hw/init.rc'))
            for name in ['system/bin/init', 'system/bin/recovery', 'system/etc/init/hw/init.rc']}
    rc = regular(entries, 'system/etc/init/hw/init.rc').decode()
    need('import /init.recovery.r97.rc\n' in rc, 'R97 RC import missing')
    for service in ['recovery', 'charger']:
        need('service ' + service + ' /system/bin/' + service + '\n    disabled\n' in rc,
             'unconditional ' + service + ' startup')
    raw = regular(entries, 'r97-runtime/module-plan.json')
    need(pin(raw)['sha256'] == MODULE_PLAN_SHA256, 'unreviewed module plan')
    plan = json.loads(raw)
    need(not plan.get('compile_only'), 'compile-only module plan cannot be paired')
    need(plan['runtime_identity'] == RUNTIME_ID and plan['MCA_count'] == 46, 'runtime identity')
    controls = {
        'firststage.txt': '\n'.join(plan['firststage'])+'\n',
        'allowed-live.txt': '\n'.join(sorted(set(plan['firststage'])|{r['name'] for r in plan['modules']}))+'\n',
        'modules.sha256': ''.join(r['sha256']+'  modules/'+r['file']+'\n' for r in plan['modules']),
    }
    for phase in ['ui','hardware']:
        controls[phase+'.list'] = ''.join('|'.join([r['name'],r['file'],' '.join(r['args'])])+'\n'
            for r in plan['modules'] if r['phase']==phase and not r['firststage'])
    for name, text in controls.items():
        need(regular(entries,'r97-runtime/'+name)==text.encode(),'runtime control changed: '+name)
    overlays=json.loads(Path(__file__).with_name('overlay-pins.json').read_text())
    for name, expected in overlays.items():
        # init explicitly invokes /system/bin/sh; source files need no exec bit.
        need(pin(regular(entries,name))==expected,'reviewed runtime script/RC changed: '+name)
    for row in plan['modules']:
        data = regular(entries, 'r97-runtime/modules/' + row['file'])
        need(pin(data) == {'bytes': row['bytes'], 'sha256': row['sha256']}, 'module changed: ' + row['file'])
    need(len(plan['modules']) == 126, 'module inventory count')
    expected={'r97-runtime/'+n for n in controls}|{'r97-runtime/module-plan.json'}|{
        'r97-runtime/modules/'+r['file'] for r in plan['modules']}|{n for n in overlays if n.startswith('r97-runtime/')}
    actual={n for n,row in entries.items() if n.startswith('r97-runtime/') and not stat.S_ISDIR(row['mode'])}
    need(actual==expected,'unexpected or missing runtime files')
    return {'image': image_pin, 'pins': pins, 'runtime_identity': RUNTIME_ID,
            'module_count': 126, 'generic_init_pin_preserved': True,
            'recovery_init_symlink': '/system/bin/init', 'device_tested': False}

if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('image')
    a = p.parse_args()
    print(json.dumps(verify_candidate(a.image), indent=2))
