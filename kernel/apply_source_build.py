#!/usr/bin/env python3
"""Merge this kernel adapter into an existing myron checkout, preserving other adaptations."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


HEADER_CONFIG = b'''# The exported UAPI tree is flat; declare every header for sbox retention.
$(call soong_config_set,lineageGlobalVars,preexported_kernel_headers,true)
$(call soong_config_set,lineageGlobalVars,preexported_kernel_headers_root,.)
'''
HEADER_ANCHOR = b'TARGET_KERNEL_SOURCE := $(KERNEL_PATH)/kernel-headers\n'


def adapter_bytes(path, destination, previous):
    data = path.read_bytes()
    if not destination.exists():
        return data
    current = destination.read_bytes()
    # Preserve the exact optional header repair when updating the kernel adapter.
    # Normalize only this reviewed insertion; unknown changes still fail closed.
    keep_headers = (path.name == 'BoardConfigKernel.mk' and
                    current.count(HEADER_ANCHOR + HEADER_CONFIG) == 1 and
                    current.count(HEADER_CONFIG) == 1 and HEADER_CONFIG not in data)
    normalized = current.replace(HEADER_CONFIG, b'', 1) if keep_headers else current
    if normalized != data:
        known = previous.get(path.name, [])
        known = [known] if isinstance(known, str) else known
        if hashlib.sha256(normalized).hexdigest() not in known:
            sys.exit('Existing adapter differs: ' + str(destination))
    if keep_headers:
        if data.count(HEADER_ANCHOR) != 1:
            sys.exit('Cannot preserve exported header configuration: ' + str(destination))
        data = data.replace(HEADER_ANCHOR, HEADER_ANCHOR + HEADER_CONFIG, 1)
    return data


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('rom_root', type=Path)
    p.add_argument('--apply', action='store_true')
    args = p.parse_args()
    source = Path(__file__).resolve().parents[1]
    target = args.rom_root.resolve() / 'device/xiaomi/myron'
    if source == target:
        sys.exit('Use a separate clone of the source adapter for merging into an existing tree.')
    board = target / 'BoardConfig.mk'
    old = board.read_text()
    marker = 'include $(DEVICE_PATH)/kernel/BoardConfigKernel.mk'
    if marker in old:
        new = old
    else:
        # Match the exact original kernel block, leaving policy and other local edits intact.
        reference = subprocess.check_output(['git', '-C', str(source), 'show', 'HEAD:kernel/upstream-kernel-block.txt'], text=True) if not (source / 'kernel/upstream-kernel-block.txt').exists() else (source / 'kernel/upstream-kernel-block.txt').read_text()
        if old.count(reference) != 1:
            sys.exit('Kernel block has local changes; refusing to replace it. Review kernel/BoardConfigKernel.mk and merge manually.')
        new = old.replace(reference, '# Source-built kernel and matching modules (device-owned Kleaf rule).\n' + marker + '\n\n')
    writes = {board: new.encode()}
    dep = target / 'evolution.dependencies'
    deps = json.loads(dep.read_text())
    entry = next(d for d in json.loads((source / 'evolution.dependencies').read_text()) if d['target_path'] == 'kernel/xiaomi/myron-build')
    existing = [d for d in deps if d['target_path'] == entry['target_path']]
    if existing and existing != [entry]:
        sys.exit('Existing build-entry dependency differs; refusing to overwrite.')
    if not existing:
        deps.append(entry)
    writes[dep] = (json.dumps(deps, indent=2) + '\n').encode()
    previous_path = source / 'kernel/previous-adapter.json'
    previous = json.loads(previous_path.read_text())['files'] if previous_path.exists() else {}
    for path in sorted((source / 'kernel').iterdir()):
        if path.is_file():
            dst = target / 'kernel' / path.name
            writes[dst] = adapter_bytes(path, dst, previous)
    android = target / 'Android.mk'
    block = (source / 'Android.mk').read_bytes()
    if android.exists():
        current = android.read_bytes()
        if b'/kernel/build.mk' not in current:
            writes[android] = current.rstrip() + b'\n\n' + block
        elif block not in current:
            sys.exit('Existing Android.mk kernel rule differs; merge manually.')
    else:
        writes[android] = block
    # Validate every destination before any write.
    for dst in writes:
        if dst.is_symlink() or not dst.resolve().is_relative_to(target.resolve()):
            sys.exit('Redirected destination: ' + str(dst))
    changed = [dst for dst, data in writes.items() if not dst.exists() or dst.read_bytes() != data]
    for dst in changed:
        print(('WRITE ' if args.apply else 'CHECK ') + str(dst))
    if args.apply:
        for dst in changed:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(writes[dst])
    print(f'{len(changed)} files; policy, common tree and ROM sources are not edited.')


if __name__ == '__main__':
    main()
