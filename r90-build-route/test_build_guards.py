#!/usr/bin/env python3
"""Exercise actual R90 source/patch/inventory guards against an exact R89 snapshot."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
from apply_temp_schema import (QUICK, PARENT, WRITES, apply, check_overlay, parent_contracts,
                                  parent_snapshot_pins, pin, require, safe, source_contract)
from build_temp_schema import OverlayBoundary, load_engine, reconstruct_parent


def must_reject(operation, name):
    try:
        operation()
    except ValueError:
        return name
    raise AssertionError('Guard accepted invalid input: ' + name)


def copy_snapshot(source, destination, pins):
    for name, expected in pins.items():
        original = safe(source, name)
        require(pin(original.read_bytes()) == expected, 'Invalid R89 test snapshot: ' + name)
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
    source = source_contract(repo / 'r90-build-route')
    passed = []
    with tempfile.TemporaryDirectory(prefix='r90-build-guards-') as temporary:
        root = Path(temporary)
        before = args.before_root.resolve() if args.before_root else root / 'before'
        if args.before_root is None:
            before.mkdir()
            reconstruct_parent(repo, before)
        workspace = root / 'workspace'
        copy_snapshot(before, workspace, pins)
        apply(workspace, repo / 'r90-build-route')
        apply(workspace, repo / 'r90-build-route', verify=True)
        passed.append('exact_R89_to_R90_overlay_and_postimage')
        passed.append(must_reject(lambda: apply(workspace, repo / 'r90-build-route'), 'double_apply'))
        actual_quick = safe(workspace, QUICK).read_bytes()
        safe(workspace, QUICK).write_bytes(actual_quick + b'\n')
        passed.append(must_reject(lambda: apply(workspace, repo / 'r90-build-route', verify=True),
                                  'changed_production_postimage'))
        safe(workspace, QUICK).write_bytes(actual_quick)
        guard = source['read_only_guards'][0]['path']
        guarded = safe(workspace, guard).read_bytes()
        safe(workspace, guard).write_bytes(guarded + b'\n')
        passed.append(must_reject(lambda: apply(workspace, repo / 'r90-build-route', verify=True),
                                  'changed_inherited_guard'))
        safe(workspace, guard).write_bytes(guarded)
        passed.append(must_reject(lambda: safe(workspace, '../escape'), 'parent_path_escape'))
        passed.append(must_reject(lambda: safe(workspace, '/absolute'), 'absolute_path'))
        (workspace / 'symlink').symlink_to(workspace, target_is_directory=True)
        passed.append(must_reject(lambda: safe(workspace, 'symlink/anything'), 'symlink_path'))
        # Make a private contract fixture. Mutations never touch repository files.
        fixture = root / 'repo'
        shutil.copytree(repo / 'r90-build-route', fixture / 'r90-build-route',
                        ignore=shutil.ignore_patterns('__pycache__'))
        (fixture / 'r89-build-route').mkdir()
        for name in ('build-contract.json', 'SOURCE-CONTRACT.json'):
            shutil.copy2(repo / 'r89-build-route' / name, fixture / 'r89-build-route' / name)
        route = fixture / 'r90-build-route'
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
    boundary_tests(repo, before_snapshot=None, passed=passed)
    print(json.dumps({'status': 'PASS_R90_BUILD_GUARDS', 'cases': passed,
                      'count': len(passed), 'hardware_tested': False}))


def boundary_tests(repo, before_snapshot, passed):
    from types import SimpleNamespace
    from unittest.mock import patch
    import subprocess
    r88_source = json.loads((repo / 'r88-build-route/SOURCE-CONTRACT.json').read_bytes())
    r88_pins = parent_snapshot_pins(r88_source)
    r87_digests = {name: value['sha256'] for name, value in r88_pins.items()}
    for row in r88_source['writes']:
        r87_digests[row['path']] = row['before']['sha256']
    original_run = subprocess.run
    with tempfile.TemporaryDirectory(prefix='r90-boundary-') as temporary:
        workspace = Path(temporary)
        reconstruct_parent(repo, workspace)
        for name in ('bq27z561.c', 'mca_strategy_quickchg.c'):
            source = repo / 'r89-build-route/preimage' / name
            target = next(path for path in r88_pins if path.endswith('/' + name))
            safe(workspace, target).write_bytes(source.read_bytes())
        r88_bytes = {name: safe(workspace, name).read_bytes() for name in r88_pins}
        events = []
        def verify_r88(root, *args):
            for name, expected in r88_pins.items():
                require(pin(safe(root, name).read_bytes()) == expected, 'Boundary is not exact R88')
            events.append('R88_verified')
            return {'status': 'PASS_R88_BOUNDARY_FIXTURE'}
        engine = SimpleNamespace(check=lambda _: (), apply=lambda *args, **kwargs: None,
            verify_postimages=verify_r88, parent_postimages=lambda _: dict(r87_digests))
        boundary = OverlayBoundary(engine, repo)
        def run(command, **kwargs):
            if len(command) > 2 and command[2].endswith('/test_source.py'):
                which = Path(command[2]).parent.name
                if which == 'r89-build-route':
                    boundary.r89.apply(workspace, repo / which, verify=True)
                    events.append('R89_tested')
                elif which == 'r90-build-route':
                    apply(workspace, repo / which, verify=True)
                    events.append('R90_tested')
                else:
                    raise AssertionError('Unexpected source test command')
                return SimpleNamespace(returncode=0, stdout='boundary fixture only\n', stderr='')
            return original_run(command, **kwargs)
        passed.append(must_reject(lambda: boundary.finalize(None, None, None, {}, {}),
                                  'finalize_before_compile'))
        with patch('subprocess.run', side_effect=run):
            boundary.prebuild_or_postbuild(workspace, repo, None, None, None, repo / 'r88-build-route')
        require(events == ['R88_verified', 'R89_tested', 'R90_tested'], 'Source preparation/test order changed')
        passed.append('R88_R89_R90_exact_prebuild_order')
        boundary.prebuild_or_postbuild(workspace, repo, None, None, None, repo / 'r88-build-route')
        boundary.apply_dispatch(workspace, repo / 'r88-build-route', verify=True)
        passed.append('second_boundary_and_postbuild_dispatch')
        passed.append(must_reject(lambda: boundary.apply_dispatch(workspace, repo / 'r88-build-route'),
                                  'reprepare_after_overlay'))
        passed.append(must_reject(lambda: boundary.prebuild_or_postbuild(workspace, repo, None, None, None,
                                                                       repo / 'r88-build-route'),
                                  'third_verification_boundary'))
        quick = safe(workspace, QUICK)
        quick.write_bytes(quick.read_bytes() + b'\n')
        passed.append(must_reject(lambda: boundary.verify_all(workspace), 'whole_source_postbuild_mutation'))
        for failed_round in ('r89-build-route', 'r90-build-route'):
            workspace = Path(temporary) / failed_round
            for name, data in r88_bytes.items():
                target = safe(workspace, name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            boundary = OverlayBoundary(engine, repo)
            def failing_run(command, **kwargs):
                result = run(command, **kwargs)
                if len(command) > 2 and command[2].endswith('/test_source.py') and Path(command[2]).parent.name == failed_round:
                    return SimpleNamespace(returncode=1, stdout='', stderr='injected source-test failure\n')
                return result
            with patch('subprocess.run', side_effect=failing_run):
                passed.append(must_reject(lambda: boundary.prebuild_or_postbuild(workspace, repo, None, None, None,
                                                                               repo / 'r88-build-route'),
                                          failed_round + '_test_failure_blocks_prebuild'))
            require(not boundary.applied, 'Failed source tests must not mark the boundary ready')
            passed.append(must_reject(lambda: boundary.finalize(None, None, None,
                                                               {'success': True, 'validation_compiled': True}, {}),
                                      failed_round + '_test_failure_blocks_finalize'))



if __name__ == '__main__':
    main()
