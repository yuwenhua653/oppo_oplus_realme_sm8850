#!/usr/bin/env python3
"""Run unchanged, hash-locked R18 preparation steps; never run its build stage."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def main():
    lock = json.loads((HERE / 'legacy-preparation-lock.json').read_text())
    root = Path(os.environ['WORKSPACE_DIR']).resolve()
    package = Path(os.environ['PACKAGE_DIR']).resolve()
    reports = root / 'integration-reports'
    reports.mkdir(parents=True, exist_ok=True)
    for row in lock['steps']:
        path = HERE / row['file']
        if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Legacy preparation helper mismatch: ' + row['file'])
    for row in lock['steps']:
        print('R55 preparation:', row['source_step'], flush=True)
        subprocess.run(['bash', str(HERE / row['file'])], check=True)
    subprocess.run(['python3', str(package.parent / 'myron-adaptation-r12/install_hooks.py'),
                    '--package', str(package), '--workspace', str(root)], check=True)
    (reports / 'r55-legacy-preparation.json').write_text(json.dumps(lock, indent=2) + '\n')


if __name__ == '__main__':
    main()
