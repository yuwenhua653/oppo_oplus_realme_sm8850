#!/usr/bin/env python3
"""Install only the reviewed standalone native sources into a new build folder."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAMES = {'Android.bp','readiness.c','readiness.h','android_io.c','android_io.h',
         'watchdog.c','watchdog.h','broker_main.c','client_main.c'}

def main():
    source = HERE/'readiness'
    manifest = json.loads((source/'SOURCE-FILES.json').read_text())
    if {r['path'] for r in manifest} != NAMES or len(manifest) != len(NAMES):
        raise ValueError('wrong readiness source inventory')
    for row in manifest:
        p=source/row['path'];data=p.read_bytes()
        if p.is_symlink() or len(data)!=row['bytes'] or hashlib.sha256(data).hexdigest()!=row['sha256']:
            raise ValueError('readiness source drift: '+row['path'])
        data.decode('utf-8')
    if sys.argv[1] == '--check-only':
        print('PASS fixed readiness source inventory and hashes')
        return
    root=Path(sys.argv[1]).resolve()
    target=root/'system/r99_readiness'
    if target.exists():
        raise ValueError('refusing to overwrite source folder')
    target.mkdir(parents=True)
    for row in manifest:
        shutil.copyfile(source/row['path'],target/row['path'])
    print('Installed compile-only native source folder; no init_rc or product-package integration')

if __name__ == '__main__':
    main()
