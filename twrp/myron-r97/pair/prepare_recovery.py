#!/usr/bin/env python3
"""Locally inject the private exact R96 runtime into a source-only CI image."""
import argparse
import hashlib
import importlib
import json
import stat
import sys
from pathlib import Path
from read_candidate import need, pin, read_image, verify_candidate, MODULE_PLAN_SHA256, check_boot_layout

def runtime_files(root):
    root = Path(root)
    raw = (root / 'module-plan.json').read_bytes()
    need(pin(raw)['sha256'] == MODULE_PLAN_SHA256, 'exact reviewed plan')
    plan = json.loads(raw)
    controls = {
        'firststage.txt': '\n'.join(plan['firststage'])+'\n',
        'allowed-live.txt': '\n'.join(sorted(set(plan['firststage'])|{r['name'] for r in plan['modules']}))+'\n',
        'modules.sha256': ''.join(r['sha256']+'  modules/'+r['file']+'\n' for r in plan['modules']),
    }
    for phase in ['ui', 'hardware']:
        controls[phase+'.list'] = ''.join('|'.join([r['name'],r['file'],' '.join(r['args'])])+'\n'
            for r in plan['modules'] if r['phase']==phase and not r['firststage'])
    files = {'module-plan.json': raw}
    for name, value in controls.items():
        need((root/name).read_text() == value, 'control bytes '+name)
        files[name] = value.encode()
    for row in plan['modules']:
        name = 'modules/'+row['file']
        b = (root/name).read_bytes()
        need(pin(b) == {'bytes': row['bytes'], 'sha256': row['sha256']}, 'module bytes '+name)
        files[name] = b
    need(not any(p.is_symlink() for p in root.rglob('*')), 'no runtime input symlinks')
    need({p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()} == set(files), 'runtime inventory')
    return files

def prepare(candidate, runtime, image_tools, out):
    candidate, out = Path(candidate), Path(out)
    need(not out.exists(), 'output already exists')
    image, before = read_image(candidate)
    need(stat.S_ISLNK(before['init']['mode']) and before['init']['data'] == b'/system/bin/init', 'original /init link')
    marker = 'R97-COMPILE-ONLY-NOT-FLASHABLE'
    need(marker in before and stat.S_ISREG(before[marker]['mode']), 'source-only candidate marker required')
    removals = {marker} | check_boot_layout(before, allow_known_vendor_link=True)
    files = runtime_files(runtime)
    sys.path.insert(0, str(Path(image_tools).resolve()))
    im = importlib.import_module('build_images')
    codec = im.LegacyLz4()
    header = im.android_header(image, False)
    raw = codec.decompress(image[4096:4096+header['ramdisk_bytes']])
    replacements, additions = {}, []
    needed_dirs = {'r97-runtime', 'r97-runtime/modules'}
    for d in sorted(needed_dirs):
        if d not in before:
            additions.append((d, b'', 0o40755))
        else:
            need(stat.S_ISDIR(before[d]['mode']), 'runtime directory type')
    for name, data in files.items():
        target = 'r97-runtime/'+name
        if target in before:
            need(stat.S_ISREG(before[target]['mode']), 'runtime replacement file type')
            replacements[target] = data
        else:
            additions.append((target, data, 0o100644))
    packed, _, _, changes = im.rebuild_cpio(raw, lambda entry:entry['name'] in removals, replacements, additions)
    payload, _ = im.recovery_payload(image, codec.compress(packed, 9))
    assembled, avb = im.append_avb(payload, image, 'recovery', None)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(assembled)
    reviewed = verify_candidate(out)
    _, after = read_image(out)
    expected = {'r97-runtime/'+n for n in files}
    for n, row in before.items():
        if n not in expected and n not in removals:
            need(after[n] == row, 'non-runtime file changed: '+n)
    need(set(after) == (set(before)-removals)|expected|needed_dirs, 'recovery inventory')
    reviewed.update({'ci_candidate': pin(image), 'local_injection_only': sorted(expected),
                     'removed_compile_and_layout_entries': sorted(removals),
                     'AVB': avb, 'device_tested': False})
    (out.with_suffix('.review.json')).write_text(json.dumps(reviewed, indent=2)+'\n')
    return reviewed

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--candidate',required=True)
    p.add_argument('--runtime',required=True)
    p.add_argument('--image-tools',required=True)
    p.add_argument('--out',required=True)
    a=p.parse_args()
    print(json.dumps(prepare(a.candidate,a.runtime,a.image_tools,a.out),indent=2))
