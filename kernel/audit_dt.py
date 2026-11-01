#!/usr/bin/env python3
"""Audit DT-only compiler output; never publish incomplete-profile flash images."""
import argparse
import copy
import json
from pathlib import Path
import tempfile
import source_dt as dt

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--compiled', required=True, type=Path)
    p.add_argument('--report', required=True, type=Path)
    for name in ('fdtoverlay', 'fdtoverlaymerge', 'fdtput', 'mkdtboimg'):
        p.add_argument('--' + name, default=name)
    a = p.parse_args()
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.unlink(missing_ok=True)
    profile = json.loads((HERE / 'dt-profile.json').read_text())
    files, missing = dt.compiled_catalog(a.compiled, profile)
    matches = []
    trees, errors = dt.preflight(files, profile, missing, matches)
    report = {'kind': 'dt-only-audit', 'device_tested': False, 'full_kernel_compiled': False,
        'flash_images_emitted': False, 'profile_sha256': dt.sha(HERE / 'dt-profile.json'),
        'compile_manifest_sha256': dt.sha(a.compiled / 'dt-compile.json'),
        'dts_commit': profile['dts_commit'], 'preflight_errors': errors,
        'compiled_inputs': len(files), 'variants': [], 'reviewed_matches': matches}
    try:
        # ID-blocked variants stay blocked. Do not remove the production gate or mutate their IDs.
        blocked = {e.get('base') for e in errors}
        allowed = [b for b in profile['bases'] if b['file'] not in blocked]
        dt.require(not any('base' not in e for e in errors), 'Shared input failure')
        if allowed:
            subset = copy.deepcopy(profile)
            subset['bases'] = allowed
            # Temporary containers exercise the real assembler but never become ROM inputs.
            with tempfile.TemporaryDirectory(prefix='myron-dt-audit-') as temporary:
                out = Path(temporary)
                dt.assemble(files, trees, subset, out, a)
                for i, base in enumerate(allowed):
                    merged = out / 'work' / ('merged-%02d.dtb' % i)
                    nodes = dt.fdt(merged.read_bytes())
                    report['variants'].append({'base': base['file'], 'status': 'structural_checks_passed',
                        'merged_sha256': dt.sha(merged), 'node_count': len(nodes)})
        for base in profile['bases']:
            if base['file'] in blocked:
                report['variants'].append({'base': base['file'], 'status': 'blocked_by_preflight'})
        report['all_variants_passed'] = not errors and len(allowed) == len(profile['bases'])
        report['audit_completed'] = True
    except (OSError, ValueError, KeyError) as error:
        report.update(audit_completed=False, failure=str(error), all_variants_passed=False)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(report, indent=2))
    # An incomplete profile is a failure, even if diagnostics completed.
    return 0 if report['all_variants_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
