#!/usr/bin/env python3
"""Validate each actual GNU Make shell invocation without executing build commands."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--depmod', default='/usr/sbin/depmod')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    records = (args.out / 'recipes.jsonl').resolve()
    records.write_text('')
    with tempfile.TemporaryDirectory(prefix='myron-recipe-check-') as tmp:
        folder = Path(tmp)
        # Name it bash so GNU Make applies the same POSIX-shell prefix handling.
        shell = folder / 'bash'
        shell.write_text('''#!/usr/bin/env python3
import json, os, subprocess, sys
command = sys.argv[sys.argv.index('-c') + 1]
with open(os.environ['MYRON_CI_RECIPE_RECORDS'], 'a') as stream:
    stream.write(json.dumps(command) + '\\n')
sys.exit(subprocess.run(['/bin/bash', '-n', '-c', command]).returncode)
''')
        shell.chmod(0o755)
        extra = folder / 'syntax.mk'
        # Target-specific SHELL leaves read-only parse-time $(shell ...) intact.
        # It is inherited by every dependency; no build recipe is executed.
        extra.write_text(f'ci-all: SHELL := {shell}\n')
        result = subprocess.run(
            ['make', '--no-print-directory', '-s', '-B', '-j1',
             '-f', 'device/xiaomi/myron/kernel/ci/standalone.mk', '-f', str(extra),
             f'DEPMOD={args.depmod}', 'ci-all'],
            env={**os.environ, 'MYRON_CI_RECIPE_RECORDS': str(records)})
        if result.returncode:
            raise SystemExit(result.returncode)
    commands = [json.loads(line) for line in records.read_text().splitlines()]
    image = [c for c in commands if 'Building Kernel Image (' in c]
    assert len(image) == 1, 'Expected one complete kernel image recipe'
    for marker in ('Building Kernel Modules', 'Building and Installing External Kernel Modules',
                   'system_dlkm/lib/modules', 'vendor_dlkm/lib/modules',
                   'vendor_ramdisk/lib/modules', 'recovery/root/lib/modules'):
        assert marker in image[0], f'Module path absent from image recipe: {marker}'
    assert any('headers_install' in c for c in commands), 'Header recipe was not checked'
    report = {'success': True, 'shell_invocations': len(commands),
              'module_partition_recipes': 4, 'build_commands_executed': False}
    (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
