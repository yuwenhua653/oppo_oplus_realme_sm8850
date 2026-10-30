#!/usr/bin/env python3
"""Check the HEAD of every source project before applying adaptation patches."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('pins', HERE / 'validate-inputs.py')
pins = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pins)

def main():
    root, output = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
    rows = pins.manifest()
    for row in rows:
        path = root / row['path']
        if not path.is_dir() or root not in path.resolve().parents:
            raise ValueError('unsafe/missing project: '+row['path'])
        head = subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
        row['actual_head'] = head
        if head != row['revision']:
            raise ValueError('project HEAD mismatch: '+row['path'])
        status = subprocess.check_output(['git','-C',str(path),'status','--porcelain','--untracked-files=no'],text=True)
        if status.strip():
            raise ValueError('modified synced source: '+row['path'])
    output.write_text(json.dumps({'status':'ALL_PINNED_PROJECT_HEADS_MATCH','projects':rows},indent=2)+'\n')
    print('PASS all '+str(len(rows))+' project HEADs, before local adaptation')

if __name__ == '__main__':
    main()
