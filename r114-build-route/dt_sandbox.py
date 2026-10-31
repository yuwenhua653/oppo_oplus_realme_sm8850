#!/usr/bin/env python3
"""Expose the nested fingerprint package to the ACK DTS sandbox explicitly."""
import hashlib
import json
from pathlib import Path
import subprocess

DT = 'vendor/qcom/sm8850-devicetrees'
TARGET = '//' + DT + ':msm_dt'
ROOT_BEFORE = 'ab466bdbeac021af9b6b9929a8c084f21e3b671a52f4f98f625e56bc23b6f4a6'
CHILD_BEFORE = '19a78d8771bc2b57a8bdafa3fdde61f67f11b97fe964b2da8d99d4e4715b6dd5'
CHILD = '''# ACK kernel_dtstree inputs for the existing fingerprint DTS package.
# The parent glob cannot cross this Bazel package boundary.
filegroup(
    name = "ack_dt_sources",
    srcs = glob([
        "**/*.dts",
        "**/*.dtsi",
        "**/*.dtso",
        "**/*.h",
        "**/*.mk",
        "**/Kbuild",
        "**/Makefile",
        "bindings/**/*",
    ]),
    visibility = ["//visibility:public"],
)
'''
ANCHOR = '    ) + [\n        "//common:kernel_aarch64_sources",\n'
REPLACEMENT = '    ) + [\n        "//' + DT + '/qcom/fingerprint:ack_dt_sources",\n        "//common:kernel_aarch64_sources",\n'

def require(ok, message):
    if not ok:
        raise ValueError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n')

def apply(root, reports):
    dt = root / DT
    top, child = dt / 'BUILD.bazel', dt / 'qcom/fingerprint/BUILD.bazel'
    before_top, before_child = top.read_text(), child.read_bytes()
    # Accept only the inherited post-patch root and the pinned candidate child.
    require(sha(before_top.encode()) == ROOT_BEFORE, 'Unexpected prepared DTS BUILD.bazel')
    require(sha(before_child) == CHILD_BEFORE, 'Unexpected fingerprint BUILD.bazel')
    nested = sorted(str(p.relative_to(dt)) for name in ('BUILD', 'BUILD.bazel')
                    for p in dt.rglob(name) if p.parent != dt)
    require(nested == ['qcom/fingerprint/BUILD.bazel'], 'Unreviewed DTS package boundary: ' + repr(nested))
    require(before_top.count(ANCHOR) == 1, 'Ambiguous DTS source-list anchor')
    after_top = before_top.replace(ANCHOR, REPLACEMENT)
    top.write_text(after_top)
    child.write_text(CHILD)
    write(reports / 'r114-dt-sandbox-patch.json', {
        'files': [
            {'path': 'BUILD.bazel', 'before': ROOT_BEFORE, 'after': sha(after_top.encode())},
            {'path': 'qcom/fingerprint/BUILD.bazel', 'before': CHILD_BEFORE, 'after': sha(CHILD.encode())}],
        'dts_contents_changed': False,
        'reason': 'Parent glob omits nested packages; export fingerprint inputs through an explicit filegroup.'})

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
