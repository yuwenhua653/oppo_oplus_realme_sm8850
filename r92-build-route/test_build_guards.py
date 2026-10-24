#!/usr/bin/env python3
"""Reject dropped providers, widened scopes, altered ancestry and wrong source images."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
from contract import (MODULE, PARENT, PROVIDER, apply, check_overlay, original_provider,
                      parents, pin, r90_snapshot, require, safe)
from build_pd_provider import Boundary, reconstruct_parent


def reject(operation, label):
    try:
        operation()
    except (ValueError, FileNotFoundError):
        return label
    raise AssertionError('Invalid input passed: ' + label)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parent.parent)
    a = p.parse_args()
    repo = a.repo_root.resolve()
    contract = check_overlay(repo)
    _, source = parents(repo)
    reference = r90_snapshot(source)
    passed = []
    # Run the real complete parent chain instead of substituting its output.
    boundary = Boundary(repo)
    checked, *_ = boundary.check(repo)
    require(checked == contract and len(checked['validation_only_modules']) == 48,
            'Full-parent input check failed to select exact 48 targets')
    passed.append('full_unchanged_R90_parent_chain_then_exact_48_scope')
    with tempfile.TemporaryDirectory(prefix='r92-guards-') as temporary:
        root = Path(temporary)
        workspace = root / 'workspace'
        workspace.mkdir()
        reconstruct_parent(repo, workspace)
        require(pin(safe(workspace, PROVIDER).read_bytes()) == pin(original_provider(repo)),
                'Negative control is not exact original provider')
        apply(workspace, repo)
        apply(workspace, repo, verify=True)
        passed.append('one_provider_patch_after_exact_R90')
        passed.append(reject(lambda: apply(workspace, repo), 'double_provider_patch_rejected'))
        final = safe(workspace, PROVIDER).read_bytes()
        safe(workspace, PROVIDER).write_bytes(final + b'\n')
        passed.append(reject(lambda: apply(workspace, repo, verify=True), 'modified_provider_postimage_rejected'))
        safe(workspace, PROVIDER).write_bytes(final)
        first = next(iter(reference))
        before = safe(workspace, first).read_bytes()
        safe(workspace, first).write_bytes(before + b'\n')
        passed.append(reject(lambda: apply(workspace, repo, verify=True), 'inherited_R90_source_mutation_rejected'))
        safe(workspace, first).write_bytes(before)
        passed.append(reject(lambda: safe(workspace, '../escape'), 'parent_path_escape_rejected'))
        passed.append(reject(lambda: safe(workspace, '/absolute'), 'absolute_path_rejected'))
        (workspace / 'linked').symlink_to(workspace, target_is_directory=True)
        passed.append(reject(lambda: safe(workspace, 'linked/anything'), 'symlink_path_rejected'))
        fixture = root / 'fixture'
        shutil.copytree(repo / 'r92-build-route', fixture / 'r92-build-route', ignore=shutil.ignore_patterns('__pycache__'))
        (fixture / 'r90-build-route').mkdir()
        for name in ('build-contract.json', 'SOURCE-CONTRACT.json'):
            shutil.copy2(repo / 'r90-build-route' / name, fixture / 'r90-build-route' / name)
        path = fixture / 'r92-build-route/build-contract.json'
        exact = path.read_bytes()
        def changed(key, value):
            data = json.loads(exact)
            data[key] = value
            path.write_text(json.dumps(data))
            try:
                return check_overlay(fixture)
            finally:
                path.write_bytes(exact)
        passed.append(reject(lambda: changed('validation_only_modules', contract['validation_only_modules'][:-1]),
                             'missing_PD_provider_target_rejected'))
        passed.append(reject(lambda: changed('validation_only_modules', contract['validation_only_modules'] + [MODULE]),
                             'duplicate_or_extra_target_rejected'))
        edited = copy.deepcopy(contract['validation_only_modules'])
        edited[0]['target'] += '-unreviewed'
        passed.append(reject(lambda: changed('validation_only_modules', edited), 'inherited_target_change_rejected'))
        passed.append(reject(lambda: changed('baseline_kernel_release', 'unexpected'), 'kernel_release_change_rejected'))
        passed.append(reject(lambda: changed('activation_allowed', True), 'premature_activation_rejected'))
        passed.append(reject(lambda: changed('source_contract', {'bytes': 0, 'sha256': '0'*64}),
                             'unbound_source_contract_rejected'))
        parent = fixture / PARENT
        parent_exact = parent.read_bytes()
        parent.write_bytes(parent_exact + b'\n')
        passed.append(reject(lambda: check_overlay(fixture), 'parent_contract_tampering_rejected'))
        parent.write_bytes(parent_exact)
        patch = fixture / 'r92-build-route/patches/pd-provider.patch'
        patch_exact = patch.read_bytes()
        patch.write_bytes(patch_exact + b'\n')
        passed.append(reject(lambda: check_overlay(fixture), 'provider_patch_tampering_rejected'))
        patch.write_bytes(patch_exact)
        (fixture / 'r92-build-route/unlocked.py').write_text('# not reviewed\n')
        passed.append(reject(lambda: check_overlay(fixture), 'unlocked_file_rejected'))
    boundary_tests(repo, passed)
    print(json.dumps({'schema': 1, 'status': 'PASS_R92_BUILD_GUARDS',
                      'checks': passed, 'count': len(passed), 'hardware_tested': False}))



def boundary_tests(repo, passed):
    from types import SimpleNamespace
    from unittest.mock import patch
    import subprocess
    original_run = subprocess.run
    with tempfile.TemporaryDirectory(prefix='r92-boundary-') as temporary:
        base = Path(temporary)
        before = base / 'before'
        before.mkdir()
        reconstruct_parent(repo, before)
        for failure in (False, True):
            workspace = base / ('failed-test' if failure else 'valid')
            shutil.copytree(before, workspace)
            (workspace / 'integration-reports').mkdir()
            boundary = Boundary(repo)
            events = []
            # R90 has its independent real boundary regression suite. This
            # fixture supplies its verified final state to test only R92 order.
            def parent_boundary(*args):
                boundary.parent.verify_calls += 1
                boundary.parent.applied = True
                for name, expected in r90_snapshot(parents(repo)[1]).items():
                    require(pin(safe(workspace, name).read_bytes()) == expected,
                            'R92 boundary altered parent production source')
                events.append('R90_complete')
                return {'status': 'R90_BOUNDARY_FIXTURE'}
            boundary.parent.prebuild_or_postbuild = parent_boundary
            boundary.parent.verify_all = lambda root: {'status': 'R90_BOUNDARY_FIXTURE'}
            def run(command, **kwargs):
                if len(command) > 2 and command[2].endswith('/r92-build-route/test_source.py'):
                    apply(workspace, repo, verify=True)
                    events.append('R92_actual_postimage_tested')
                    return SimpleNamespace(returncode=1 if failure else 0,
                        stdout='explicit boundary fixture\n', stderr='')
                return original_run(command, **kwargs)
            passed.append(reject(lambda: boundary.finalize(None, None, None, {}, {}),
                                 'finalize_without_complete_boundary_rejected'))
            with patch('subprocess.run', side_effect=run):
                call = lambda: boundary.prebuild_or_postbuild(workspace, repo, None, None, None,
                                                               repo / 'r88-build-route')
                if failure:
                    passed.append(reject(call, 'provider_host_failure_blocks_prebuild'))
                    require(not boundary.applied, 'Failed R92 test marked boundary prepared')
                    passed.append(reject(lambda: boundary.finalize(None, None, None,
                        {'success': True, 'validation_compiled': True}, {}),
                        'provider_host_failure_blocks_finalize'))
                else:
                    call()
                    require(events == ['R90_complete', 'R92_actual_postimage_tested'],
                            'R92 applied/tested before complete parent boundary')
                    passed.append('R90_then_R92_exact_prebuild_order')
                    call()
                    passed.append('single_postbuild_boundary_passed')
                    passed.append(reject(call, 'third_R92_boundary_rejected'))


if __name__ == '__main__':
    main()
