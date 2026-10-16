#!/usr/bin/env python3
"""Real locked-byte regressions for the prior extra-LF and partial-write failures."""
import hashlib
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import apply_battery as layer
from check_battery_inputs import check

HERE = Path(__file__).resolve().parent


def main():
    lock = json.loads((HERE / 'battery-write-lock.json').read_text())
    contract = json.loads((HERE / 'battery-contract.json').read_text())
    check(HERE.parent, contract)
    checks = []
    with tempfile.TemporaryDirectory(prefix='r61-preimages-') as tmp:
        root = Path(tmp)
        originals = {}
        for relative in lock['git_heads']:
            (root / relative).mkdir(parents=True, exist_ok=True)
        upstream_fixtures = {}
        for row in lock.get('upstream_files', []):
            key = row['repo'] + '/' + row['path']
            data = (HERE.parent / row['source']).read_bytes()
            assert hashlib.sha256(data).hexdigest() == row['sha256']
            target = root / key
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            upstream_fixtures[key] = data
        for row in lock['writes']:
            path = root / row['destination']
            path.parent.mkdir(parents=True, exist_ok=True)
            data = (HERE.parent / row['preimage']).read_bytes() if row['before_sha256'] is not None else None
            if data is not None:
                assert hashlib.sha256(data).hexdigest() == row['before_sha256']
                path.write_bytes(data)
            originals[row['destination']] = data

        def head(command, **kwargs):
            relative = str(Path(command[2]).relative_to(root))
            if command[3] == 'show':
                return upstream_fixtures[relative + '/' + command[4].removeprefix('HEAD:')]
            return lock['git_heads'][relative] + '\n'

        def state():
            return {name: (root / name).read_bytes() if (root / name).exists() else None for name in originals}

        with patch.object(layer.subprocess, 'check_output', head):
            checks.append('every_real_preimage_and_payload_SHA_and_byte_count_verified_before_sync')
            assert len(layer.plan(root, HERE.parent, lock)) == len(lock['writes'])
            existing = [r for r in lock['writes'] if r['before_sha256'] is not None]
            assert existing, 'Need exact existing-source preimages, not only new files'
            # Corrupt the LAST existing file: earlier valid writes must remain untouched.
            last = existing[-1]['destination']
            (root / last).write_bytes(originals[last] + b'\n')
            bad_state = state()
            try:
                layer.apply(root, HERE.parent, lock)
            except ValueError as error:
                assert 'actual_sha256=' in str(error) and 'actual_bytes=' in str(error)
                assert existing[-1]['before_sha256'] in str(error)
            else:
                raise AssertionError('Extra terminal LF incorrectly accepted')
            assert state() == bad_state
            checks.append('late_preimage_extra_LF_rejected_before_any_source_write')
            (root / last).write_bytes(originals[last])

            # A missing tracked input cannot become an implicit new file.
            (root / last).unlink()
            missing_state = state()
            try:
                layer.apply(root, HERE.parent, lock)
            except ValueError:
                pass
            else:
                raise AssertionError('Missing existing input incorrectly accepted')
            assert state() == missing_state
            checks.append('missing_existing_preimage_rejected_without_partial_writes')
            (root / last).write_bytes(originals[last])

            result = layer.apply(root, HERE.parent, lock)
            assert result['status'] == 'PASS'
            for row in lock['writes']:
                assert (root / row['destination']).read_bytes() == (HERE.parent / row['source']).read_bytes()
            checks.append('real_preimages_apply_exact_reviewed_postimages')
            assert not any(r['changed'] for r in layer.apply(root, HERE.parent, lock)['writes'])
            layer.apply(root, HERE.parent, lock, check=True)
            checks.append('exact_postimages_are_idempotent_and_checkable')

            fixed = (root / last).read_bytes()
            (root / last).write_bytes(fixed + b'\n')
            post_state = state()
            try:
                layer.apply(root, HERE.parent, lock)
            except ValueError:
                pass
            else:
                raise AssertionError('Extra terminal LF on postimage accepted')
            assert state() == post_state
            checks.append('postimage_extra_LF_rejected_without_partial_writes')
    print(json.dumps({'schema': 1, 'status': 'PASS', 'checks': checks, 'count': len(checks),
                      'kernel_built': False, 'hardware_tested': False,
                      'limits': 'Exact real changed-file preimages; Git HEAD and upstream header blob use local test fixtures. CI checks actual pinned Git trees.'}, indent=2))


if __name__ == '__main__':
    main()
