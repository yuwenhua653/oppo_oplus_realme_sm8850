#!/usr/bin/env python3
"""Merge this kernel adapter into an existing myron checkout, preserving other adaptations."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


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
            if dst.exists() and dst.read_bytes() != path.read_bytes():
                digest = hashlib.sha256(dst.read_bytes()).hexdigest()
                if previous.get(path.name) != digest:
                    sys.exit('Existing adapter differs: ' + str(dst))
            writes[dst] = path.read_bytes()
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
