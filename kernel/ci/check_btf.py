#!/usr/bin/env python3
"""Exercise the kernel's pahole flags before spending time compiling vmlinux."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import struct
import subprocess


def run(*args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


def check_btf(path, expected):
    data = path.read_bytes()
    magic, version, _, hdr, off, size, strings_off, strings_size = struct.unpack_from(
        '<HBBIIIII', data)
    assert (magic, version) == (0xEB9F, 1), 'Invalid BTF header'
    strings = data[hdr + strings_off:hdr + strings_off + strings_size]
    cursor, end = hdr + off, hdr + off + size
    names, datasec = set(), 0
    while cursor < end:
        name_off, info, _ = struct.unpack_from('<III', data, cursor)
        name = strings[name_off:strings.index(b'\0', name_off)].decode()
        kind, count = (info >> 24) & 31, info & 65535
        extra = {1: 4, 2: 0, 3: 12, 4: 12 * count, 5: 12 * count,
                 6: 8 * count, 7: 0, 8: 0, 9: 0, 10: 0, 11: 0,
                 12: 0, 13: 8 * count, 14: 4, 15: 12 * count,
                 16: 0, 17: 4, 18: 0, 19: 12 * count}[kind]
        if kind == 14:
            names.add(name)
        if kind == 15 and name == '.data..percpu':
            datasec += count
        cursor += 12 + extra
    assert cursor == end, 'Malformed BTF types'
    assert names == expected, f'BTF retained {len(names)} of {len(expected)} variables'
    assert datasec == len(expected), f'Per-CPU DATASEC has {datasec} entries'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--pahole', type=Path, required=True)
    parser.add_argument('--cc', default='cc')
    parser.add_argument('--objcopy', default='objcopy')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    pahole = str(args.pahole.resolve())
    version = run(pahole, '--version')
    match = re.fullmatch(r'v(\d+)\.(\d+)', version)
    assert match, f'Unknown pahole version: {version}'
    number = int(match[1]) * 100 + int(match[2])
    # Read the actual pinned kernel rules instead of maintaining a second flag list.
    makefile = args.out / 'flags.mk'
    makefile.write_text(
        'test-le = $(shell test $(1) -le $(2) && echo y)\n'
        'test-ge = $(shell test $(1) -ge $(2) && echo y)\n'
        f'CONFIG_PAHOLE_VERSION := {number}\n'
        'CONFIG_PAHOLE_HAS_LANG_EXCLUDE := y\n'
        f'include {args.kernel.resolve()}/scripts/Makefile.btf\n'
        'all:\n\t@echo $(PAHOLE_FLAGS)\n'
        'module-flags:\n\t@echo $(MODULE_PAHOLE_FLAGS)\n')
    flags = shlex.split(run('make', '--no-print-directory', '-s', '-f', str(makefile)))
    expected = {f'percpu_probe_{i}' for i in range(5000)}
    source = args.out / 'percpu.c'
    source.write_text(''.join(
        f'int {name} __attribute__((section(".data..percpu"), used)) = 1;\n'
        for name in sorted(expected)) + 'void _start(void) {}\n')
    elf = args.out / 'percpu.elf'
    run(args.cc, '-g', '-nostdlib', '-no-pie', '-Wl,-e,_start',
        '-Wl,--build-id=none', '-Wl,--unique=.data..percpu', str(source), '-o', str(elf))
    run(pahole, '-J', *flags, str(elf), env={**os.environ, 'LLVM_OBJCOPY': args.objcopy})
    btf = args.out / 'percpu.btf'
    btf.unlink(missing_ok=True)
    run(args.objcopy, '--dump-section', f'.BTF={btf}', str(elf))
    assert btf.exists(), 'pahole failed to create .BTF despite reporting success'
    check_btf(btf, expected)
    module_flags = shlex.split(run('make', '--no-print-directory', '-s', '-f',
                                  str(makefile), 'KBUILD_EXTMOD=probe', 'module-flags'))
    module_c, module_o = args.out / 'module.c', args.out / 'module.o'
    module_c.write_text('int module_probe(int value) { return value + 1; }\n')
    run(args.cc, '-g', '-O2', '-c', str(module_c), '-o', str(module_o))
    run(pahole, '-J', *flags, *module_flags, '--btf_base=' + str(elf), str(module_o),
        env={**os.environ, 'LLVM_OBJCOPY': args.objcopy})
    for section in ('.BTF', '.BTF.base'):
        target = args.out / ('module' + section)
        target.unlink(missing_ok=True)
        run(args.objcopy, '--dump-section', f'{section}={target}', str(module_o))
        assert target.exists() and target.stat().st_size > 24, f'Missing module {section}'
        assert target.read_bytes()[:3] == b'\x9f\xeb\x01', f'Invalid module {section}'
    report = {'pahole': version, 'flags': flags, 'percpu_variables': len(expected),
              'btf_bytes': btf.stat().st_size, 'module_flags': module_flags,
              'module_distilled_base': True, 'success': True}
    (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
