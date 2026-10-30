#!/usr/bin/env python3
"""Apply the already tested exact patch only to the pinned original init file."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from source_checks import check_source

HERE = Path(__file__).resolve().parent

def main():
    root = Path(sys.argv[1]).resolve()
    core = root/'system/core'
    lock = json.loads((HERE/'source-lock.json').read_text())
    check_source(root, 'baseline', lock)
    patch = HERE/'selector/recovery-only-permissive.patch'
    if hashlib.sha256(patch.read_bytes()).hexdigest() != lock['patch_sha256']:
        raise ValueError('wrong patch')
    subprocess.run(['git','apply','--check',str(patch)],cwd=core,check=True)
    subprocess.run(['git','apply',str(patch)],cwd=core,check=True)
    if hashlib.sha256((core/'init/selinux.cpp').read_bytes()).hexdigest() != lock['candidate_selinux_sha256']:
        raise ValueError('patched source differs')
    check_source(root, 'patched', lock)
    print('PASS exact REC-only selector applied')

if __name__ == '__main__':
    main()
