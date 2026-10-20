#!/usr/bin/env python3
"""Use scratch fixture trees only; never mutate restored shared sources."""
import json
import shutil
import tempfile
from pathlib import Path
from apply_touch_foundation import ROOT, apply

def main():
    contract = json.loads((ROOT / 'touch-write-lock.json').read_text())
    rows = contract['writes']
    with tempfile.TemporaryDirectory(prefix='apply-test-', dir=ROOT) as temp:
        root = Path(temp)
        for row in rows:
            rel = row['destination'].removeprefix('vendor/qcom/sm8850/')
            p = root / row['destination']
            p.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / 'preimage' / rel, p)
        before = {r['destination']: (root/r['destination']).read_bytes() for r in rows}
        try:
            apply(root, True)
        except ValueError:
            pass
        else:
            raise AssertionError('check accepted the old source')
        # A bad last preimage must not permit writing the first four files.
        last = root / rows[-1]['destination']
        last.write_bytes(b'foreign source\n')
        try:
            apply(root)
        except ValueError:
            pass
        else:
            raise AssertionError('unreviewed preimage accepted')
        for row in rows[:-1]:
            assert (root/row['destination']).read_bytes() == before[row['destination']]
        last.write_bytes(before[rows[-1]['destination']])
        assert apply(root)['runtime_enable'] is False
        assert apply(root, True)['status'] == 'PASS'
        assert apply(root)['status'] == 'PASS'  # Idempotent.
        first = root / rows[0]['destination']
        first.unlink()
        first.symlink_to(ROOT / rows[0]['source'])
        try:
            apply(root, True)
        except ValueError:
            pass
        else:
            raise AssertionError('symlink accepted')
    result = {'status':'PASS','tests':['old source fails check','all-before-write rejection',
              'exact postimages','idempotent apply','symlink rejected'], 'shared_inputs_modified':False}
    (ROOT / 'APPLY-TESTS.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))

if __name__ == '__main__':
    main()
