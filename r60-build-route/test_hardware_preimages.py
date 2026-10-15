#!/usr/bin/env python3
"""Exact Git-byte preimage and all-before-write regressions; no kernel build."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

import apply_hardware as integration

HERE = Path(__file__).resolve().parent
LOCK = json.loads((HERE / 'hardware-write-lock.json').read_text())
SOURCE = json.loads((HERE / 'reviews/rmnet-perf-source-provenance.json').read_text())
PERF = 'vendor/qcom/sm8850-modules/' + SOURCE['path']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def invoke(root, check=False):
    # Mock only real-Git HEAD lookup for local filesystem fixtures, never the gates.
    def head(command, **kwargs):
        relative = str(Path(command[2]).relative_to(root))
        return LOCK['git_heads'][relative] + '\n'
    with patch.object(integration.subprocess, 'check_output', head), \
         patch.object(sys, 'argv', ['apply_hardware.py', '--workspace', str(root)] +
                      (['--check'] if check else [])), \
         contextlib.redirect_stdout(io.StringIO()):
        integration.main()


def main():
    checks = []
    with tempfile.TemporaryDirectory(prefix='r60-preimage-test-') as temporary:
        root = Path(temporary)
        for relative in LOCK['git_heads']:
            (root / relative).mkdir(parents=True, exist_ok=True)
        for row in LOCK['writes']:
            target = root / row['destination']
            target.parent.mkdir(parents=True, exist_ok=True)
            data = (HERE.parent / row['source']).read_bytes()
            assert sha(data) == row['after_sha256']
            target.write_bytes(data)
        modules = root / 'vendor/qcom/sm8850-modules'
        for change in sorted((HERE / 'patches').glob('*.patch')):
            subprocess.run(['git', 'apply', '--reverse', '--check', str(change)],
                           cwd=modules, check=True, capture_output=True)
            subprocess.run(['git', 'apply', '--reverse', str(change)],
                           cwd=modules, check=True, capture_output=True)
        originals = {row['destination']: (root / row['destination']).read_bytes()
                     for row in LOCK['writes']}
        assert all(sha(originals[row['destination']]) == row['before_sha256']
                   for row in LOCK['writes'])
        raw = originals[PERF]
        assert len(raw) == SOURCE['before_bytes'] == 24917
        assert hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == SOURCE['git_blob']
        checks.append('reviewed_patch_reverse_recovers_exact_Git_preimages')

        (root / PERF).write_bytes(raw + b'\n')
        assert sha((root / PERF).read_bytes()) == SOURCE['r60_first_run_failure']['old_reference_sha256']
        try:
            invoke(root)
        except ValueError as error:
            assert 'actual_sha256=' in str(error) and 'actual_bytes=24918' in str(error)
            assert SOURCE['before_sha256'] in str(error)
        else:
            raise AssertionError('Old extra-LF preimage unexpectedly accepted')
        assert all((root / path).read_bytes() == data for path, data in originals.items() if path != PERF)
        failure = json.loads((root / 'integration-reports/r60-hardware-preflight-failure.json').read_text())
        assert failure['actual_sha256'] == sha(raw + b'\n')
        assert failure['expected_before_sha256'] == SOURCE['before_sha256']
        assert failure['expected_after_sha256'] == SOURCE['after_sha256']
        assert failure['source_writes_started'] is False
        checks.append('extra_terminal_LF_rejected_before_any_source_write_with_exact_diagnostics')

        (root / PERF).write_bytes(raw)
        invoke(root)
        for row in LOCK['writes']:
            actual = (root / row['destination']).read_bytes()
            assert actual == (HERE.parent / row['source']).read_bytes()
            assert sha(actual) == row['after_sha256']
        fixed = (root / PERF).read_bytes()
        assert len(fixed) == SOURCE['after_bytes'] == 24928
        needle = b'\trmnet_perf_set_hooks();\n\nerr2:'
        assert raw.count(needle) == 1
        assert fixed == raw.replace(needle, b'\trmnet_perf_set_hooks();\n\treturn 0;\n\nerr2:')
        checks.append('real_Git_preimage_applies_exact_payload_with_only_success_return_added')
        invoke(root)
        invoke(root, check=True)
        checks.append('exact_postimages_remain_idempotent_and_checkable')
        (root / PERF).write_bytes(fixed + b'\n')
        try:
            invoke(root)
        except ValueError:
            pass
        else:
            raise AssertionError('Old extra-LF postimage unexpectedly accepted')
        checks.append('old_extra_LF_postimage_remains_rejected')
    print(json.dumps({'schema': 1, 'status': 'PASS', 'checks': checks,
                      'count': len(checks), 'kernel_built': False,
                      'limits': 'Filesystem regression fixtures mock HEAD lookup only; production CI validates real Git HEADs.'}, indent=2))


if __name__ == '__main__':
    main()
