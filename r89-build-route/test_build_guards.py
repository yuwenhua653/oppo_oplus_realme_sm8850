#!/usr/bin/env python3
"""Exercise actual R89 source/patch/inventory guards against an exact R88 snapshot."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
from apply_probe_recovery import (BQ, PARENT, WRITES, apply, check_overlay, parent_contracts,
                                  parent_snapshot_pins, pin, require, safe, source_contract)
from build_probe_recovery import load_engine


def must_reject(operation, name):
    try:
        operation()
    except ValueError:
        return name
    raise AssertionError('Guard accepted invalid input: ' + name)


def copy_snapshot(source, destination, pins):
    for name, expected in pins.items():
        original = safe(source, name)
        require(pin(original.read_bytes()) == expected, 'Invalid R88 test snapshot: ' + name)
        target = safe(destination, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parent.parent)
    p.add_argument('--before-root', type=Path)
    args = p.parse_args()
    repo = args.repo_root.resolve()
    check_overlay(repo)
    _, old_source = parent_contracts(repo)
    pins = parent_snapshot_pins(old_source)
    source = source_contract(repo / 'r89-build-route')
    passed = []
    with tempfile.TemporaryDirectory(prefix='r89-build-guards-') as temporary:
        root = Path(temporary)
        before = args.before_root.resolve() if args.before_root else root / 'before'
        if args.before_root is None:
            before.mkdir()
            engine = load_engine(repo)
            path = repo / 'r88-build-route/test_source.py'
            spec = importlib.util.spec_from_file_location('r89_guard_parent_reconstruction', path)
            parent_test = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(parent_test)
            parent_test.reconstruct_inputs(repo, before, old_source)
            engine.apply(before, repo / 'r88-build-route')
        workspace = root / 'workspace'
        copy_snapshot(before, workspace, pins)
        apply(workspace, repo / 'r89-build-route')
        apply(workspace, repo / 'r89-build-route', verify=True)
        passed.append('exact_R88_to_R89_overlay_and_postimage')
        passed.append(must_reject(lambda: apply(workspace, repo / 'r89-build-route'), 'double_apply'))
        actual_bq = safe(workspace, BQ).read_bytes()
        safe(workspace, BQ).write_bytes(actual_bq + b'\n')
        passed.append(must_reject(lambda: apply(workspace, repo / 'r89-build-route', verify=True),
                                  'changed_production_postimage'))
        safe(workspace, BQ).write_bytes(actual_bq)
        guard = source['read_only_guards'][0]['path']
        guarded = safe(workspace, guard).read_bytes()
        safe(workspace, guard).write_bytes(guarded + b'\n')
        passed.append(must_reject(lambda: apply(workspace, repo / 'r89-build-route', verify=True),
                                  'changed_inherited_guard'))
        safe(workspace, guard).write_bytes(guarded)
        passed.append(must_reject(lambda: safe(workspace, '../escape'), 'parent_path_escape'))
        passed.append(must_reject(lambda: safe(workspace, '/absolute'), 'absolute_path'))
        (workspace / 'symlink').symlink_to(workspace, target_is_directory=True)
        passed.append(must_reject(lambda: safe(workspace, 'symlink/anything'), 'symlink_path'))
        # Make a private contract fixture. Mutations never touch repository files.
        fixture = root / 'repo'
        shutil.copytree(repo / 'r89-build-route', fixture / 'r89-build-route',
                        ignore=shutil.ignore_patterns('__pycache__'))
        (fixture / 'r88-build-route').mkdir()
        for name in ('build-contract.json', 'SOURCE-CONTRACT.json'):
            shutil.copy2(repo / 'r88-build-route' / name, fixture / 'r88-build-route' / name)
        route = fixture / 'r89-build-route'
        patch = route / source['patches'][0]['file']
        exact_patch = patch.read_bytes()
        patch.write_bytes(exact_patch + b'\n')
        passed.append(must_reject(lambda: check_overlay(fixture), 'patch_byte_tampering'))
        patch.write_bytes(exact_patch)
        build_path = route / 'build-contract.json'
        exact_build = build_path.read_bytes()
        build = json.loads(exact_build)
        build['validation_only_modules'] = build['validation_only_modules'][:-1]
        build_path.write_text(json.dumps(build))
        passed.append(must_reject(lambda: check_overlay(fixture), 'module_scope_change'))
        build_path.write_bytes(exact_build)
        (route / 'unexpected.py').write_text('# unreviewed input\n')
        passed.append(must_reject(lambda: check_overlay(fixture), 'unlocked_extra_input'))
    print(json.dumps({'status': 'PASS_R89_BUILD_GUARDS', 'cases': passed,
                      'count': len(passed), 'hardware_tested': False}))


if __name__ == '__main__':
    main()
