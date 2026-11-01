#!/usr/bin/env python3
"""Expose the nested fingerprint package to the ACK DTS sandbox explicitly."""
import hashlib
import json
from pathlib import Path
import subprocess

DT = 'vendor/qcom/sm8850-devicetrees'
TARGET = '//' + DT + ':msm_dt'
def require(ok, message):
    if not ok:
        raise ValueError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n')

def expected_inputs(dt):
    # Enumerate the declared DTS input classes independently of Bazel glob.
    result = set()
    for p in dt.rglob('*'):
        rel = p.relative_to(dt)
        if any(part.startswith('.') for part in rel.parts) or not p.is_file():
            continue
        if rel.as_posix() == 'Makefile' or (
            rel.parts[0] == 'qcom' and
            (p.suffix in ('.dts', '.dtsi', '.dtso', '.mk', '.h') or p.name in ('Makefile', 'Kbuild'))
        ) or rel.parts[0] == 'bindings' or 'qcom/fingerprint/bindings' in rel.as_posix():
            result.add(DT + '/' + rel.as_posix())
    return result

def check_inputs(expected, actual):
    missing = sorted(expected - set(actual.splitlines()))
    require(not missing, 'DTS files absent from Bazel sandbox inputs: ' + repr(missing))
    return {'success': True, 'expected_files_checked': len(expected), 'missing': missing}

def preflight(root, reports, bazel, options):
    command = bazel + ['cquery'] + options + ['--output=files', 'labels(srcs, ' + TARGET + ')']
    result = subprocess.run(command, cwd=root, capture_output=True, text=True)
    (reports / 'r114-dt-sandbox-cquery.txt').write_text(result.stdout)
    (reports / 'r114-dt-sandbox-cquery.log').write_text(result.stderr)
    report = {'success': False, 'command': command}
    try:
        require(result.returncode == 0, 'DTS sandbox input query failed; see r114-dt-sandbox-cquery.log')
        report.update(check_inputs(expected_inputs(root / DT), result.stdout))
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        write(reports / 'r114-dt-sandbox-inputs.json', report)
