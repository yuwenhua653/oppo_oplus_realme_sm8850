#!/usr/bin/env python3
"""Apply the exact R18-to-R55 Canoe ADSP/CDSP automatic boot source delta.

Requires the original pinned SoC git HEAD and the R18 SOCCP source fix first.
Only two initializer fields change. This never edits ELF modules or images.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
LOCK = json.loads((HERE / 'source-lock.json').read_text())


def require(ok, message):
    if not ok:
        raise ValueError(message)


def info(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def git(soc, *args):
    p = subprocess.run(['git', '-C', str(soc), *args], capture_output=True)
    require(p.returncode == 0, 'Git verification failed: ' + p.stderr.decode(errors='replace'))
    return p.stdout


def patch_bytes(before):
    require(info(before) == LOCK['r18_required_input'], 'Expected exact R18 source bytes; apply the R18 SOCCP fix first')
    after = before
    for name in ('canoe_adsp_resource', 'canoe_cdsp_resource'):
        pattern = rb'static const struct adsp_data ' + name.encode() + rb' = \{.*?\n\};'
        matches = list(re.finditer(pattern, after, re.S))
        require(len(matches) == 1, 'Expected one initializer: ' + name)
        match = matches[0]
        old = match[0]
        require(b'.auto_boot' not in old and old.count(b'\t.uses_elf64 = true,') == 1,
                'Unexpected initializer body: ' + name)
        new = old.replace(b'\t.uses_elf64 = true,', b'\t.uses_elf64 = true,\n\t.auto_boot = true,')
        after = after[:match.start()] + new + after[match.end():]
    require(info(after) == LOCK['r55_output'], 'Patched bytes differ from the locked result')
    return after


def apply(soc, check):
    soc = soc.resolve()
    require(Path(git(soc, 'rev-parse', '--show-toplevel').decode().strip()).resolve() == soc,
            '--soc must name the repository root')
    head = git(soc, 'rev-parse', 'HEAD').decode().strip()
    require(head == LOCK['commit'], 'Unexpected source git HEAD: ' + head)
    tracked = git(soc, 'show', 'HEAD:' + LOCK['source_path'])
    require(info(tracked) == LOCK['original'], 'Pinned HEAD source differs from lock')
    path = soc
    for part in Path(LOCK['source_path']).parts:
        path = path / part
        require(not path.is_symlink(), 'Source path contains a symlink')
    before = path.read_bytes()
    if info(before) == LOCK['r55_output']:
        return {'ok': True, 'action': 'already_applied', 'changed': False, 'source': info(before), 'head': head}
    after = patch_bytes(before)
    if check:
        return {'ok': True, 'action': 'check_ready', 'changed': False,
                'input': info(before), 'expected_output': info(after), 'head': head}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.r55-dsp-source-', dir=path.parent, delete=False) as f:
            temporary = Path(f.name)
            f.write(after)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
        require(path.read_bytes() == before, 'Source changed concurrently')
        os.replace(temporary, path)
        temporary = None
        require(path.read_bytes() == after, 'Written source verification failed')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {'ok': True, 'action': 'applied', 'changed': True,
            'input': info(before), 'output': info(after), 'head': head}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--soc', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        report = apply(args.soc, args.check)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        report = {'ok': False, 'action': 'refused', 'reason': str(exc)}
    report.update(schema=1, hardware_tested=False, requires_recompiled_module='qcom_q6v5_pas.ko')
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
