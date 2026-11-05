#!/usr/bin/env python3
"""Place the intact Kleaf workspace under kernel/xiaomi without copying its cache.

Callers must hold their build/workspace locks while planning or applying a move.
The former workspace path remains an exact relative alias for absolute cache links.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys


IGNORE_FILE = '.find-ignore'
STATE_FILE = '.myron-platform.json'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def absolute(path):
    path = Path(path).expanduser()
    require('..' not in path.parts, 'Workspace path contains ..: ' + str(path))
    return path.absolute()


def no_redirect(path, include_self=True):
    candidates = (path, *path.parents) if include_self else path.parents
    for part in candidates:
        require(not part.is_symlink(), 'Redirected workspace path: ' + str(part))


def empty_workspace(path):
    if not path.exists():
        return True
    require(path.is_dir(), 'Workspace is not a directory: ' + str(path))
    names = {p.name for p in path.iterdir()}
    if names <= {IGNORE_FILE}:
        marker = path / IGNORE_FILE
        require(not marker.is_symlink() and (not marker.exists() or marker.is_file()),
                'Redirected or invalid Soong exclusion marker: ' + str(marker))
        return True
    return False


def default_validator(entry, lock):
    # The caller normally passes its already loaded pinned builder instead.
    original = list(sys.path)
    original_bytecode = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(entry))
        spec = importlib.util.spec_from_file_location('myron_layout_builder', entry / 'build.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
    finally:
        sys.path[:] = original
        sys.dont_write_bytecode = original_bytecode
    builder.validate_source_lock(lock)
    return lambda root: builder.check_sources(root, lock)


def check_readonly(validate_sources, root):
    # git status normally refreshes the index even for a read-only preflight.
    old = os.environ.get('GIT_OPTIONAL_LOCKS')
    os.environ['GIT_OPTIONAL_LOCKS'] = '0'
    try:
        return validate_sources(root)
    finally:
        if old is None:
            os.environ.pop('GIT_OPTIONAL_LOCKS', None)
        else:
            os.environ['GIT_OPTIONAL_LOCKS'] = old


def partial_sources(root, lock):
    allowed = {STATE_FILE, IGNORE_FILE, 'out', 'integration-artifacts',
               'integration-reports', 'myron_artifact_metadata', 'MODULE.bazel.lock',
               'bazel-bin', 'bazel-out', 'bazel-testlogs', 'bazel-workspace', 'bazel-myron'}
    allowed.update(Path(row['path']).parts[0] for row in lock['projects'])
    allowed.update(Path(row['destination']).parts[0] for row in lock.get('links', []))
    require({p.name for p in root.iterdir()} <= allowed,
            'Unowned entries in incomplete kernel workspace: ' + str(root))
    complete = True
    for row in lock['projects']:
        project = root / row['path']
        if not project.exists() or (project.is_dir() and not any(project.iterdir())):
            complete = False
            continue
        gitdir = project / '.git'
        require(gitdir.is_dir() and not gitdir.is_symlink(),
                'Populated incomplete project is not a self-contained Git checkout: ' + str(project))
        def git(*args, allow_failure=False):
            run = subprocess.run(['git', '-C', str(project), *args], capture_output=True,
                                 text=True, env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'})
            require(allow_failure or run.returncode == 0,
                    'Cannot validate incomplete kernel project: ' + str(project))
            return run
        origin = git('remote', 'get-url', 'origin').stdout.strip()
        require(origin == row['url'], 'Incomplete project origin differs: ' + str(project))
        head = git('rev-parse', '--verify', 'HEAD', allow_failure=True)
        require(head.returncode != 0 or head.stdout.strip() == row['commit'],
                'Incomplete project source revision differs: ' + str(project))
        require(not git('status', '--porcelain', '--untracked-files=normal').stdout.strip(),
                'Uncommitted source changes in incomplete workspace: ' + str(project))
        require(not (project / '.scmversion').exists(), 'SCM version override: ' + str(project))
        if head.returncode != 0:
            complete = False
    return complete


def validate_prepared(root, lock, lock_hash, validate_sources, allow_incomplete=False):
    marker = root / STATE_FILE
    require(marker.is_file() and not marker.is_symlink(),
            'Missing or redirected kernel source lock marker: ' + str(marker))
    state = json.loads(marker.read_text())
    require(isinstance(state, dict) and state.get('lock_sha256') == lock_hash
            and state.get('profile') == lock.get('profile'),
            'Kernel workspace belongs to a different source lock: ' + str(root))
    ignore = root / IGNORE_FILE
    require(not ignore.is_symlink() and (not ignore.exists() or ignore.is_file()),
            'Redirected or invalid Soong exclusion marker: ' + str(ignore))
    # A linked project or external Git worktree cannot be safely renamed as a unit.
    for row in lock['projects']:
        relative = Path(row['path'])
        require(not relative.is_absolute() and '..' not in relative.parts,
                'Invalid locked project path: ' + str(relative))
        project = root / relative
        for part in (project, *project.parents):
            if part == root:
                break
            require(not part.is_symlink(), 'Redirected kernel project: ' + str(part))
        if not allow_incomplete:
            gitdir = project / '.git'
            require(gitdir.is_dir() and not gitdir.is_symlink(),
                    'Kernel project is not a self-contained Git checkout: ' + str(project))
    if allow_incomplete and not partial_sources(root, lock):
        return False
    check_readonly(validate_sources, root)
    return True


def nearest_existing(path):
    while not path.exists():
        path = path.parent
    return path


def ensure_workspace(workspace, legacy, entry, *, apply=False, validate_sources=None,
                     allow_incomplete=False):
    """Plan/apply a verified rename, or establish a fresh ignored workspace.

    Dry runs never create directories or files. Existing prepared workspaces are
    checked against the pinned lock and source revisions. No copy/reset/download
    fallback is used. A different populated destination always requires review.
    """
    workspace, entry = absolute(workspace), absolute(entry)
    legacy = absolute(legacy) if legacy is not None else None
    no_redirect(workspace)
    if legacy is not None:
        no_redirect(legacy, include_self=False)
        require(workspace != legacy and workspace not in legacy.parents and legacy not in workspace.parents,
                'New and legacy workspaces must be separate, non-nested paths')
    lock_bytes = (entry / 'sources.lock.json').read_bytes()
    lock = json.loads(lock_bytes)
    lock_hash = hashlib.sha256(lock_bytes).hexdigest()
    validate_sources = validate_sources or default_validator(entry, lock)
    legacy_alias = legacy is not None and legacy.is_symlink()
    if legacy_alias:
        expected = os.path.relpath(workspace, legacy.parent)
        require(os.readlink(legacy) == expected and legacy.resolve() == workspace,
                'Unexpected legacy workspace alias: ' + str(legacy))
        require(workspace.is_dir(), 'Legacy workspace alias has no destination: ' + str(legacy))
    destination_empty = empty_workspace(workspace)
    legacy_present = legacy is not None and not legacy_alias and legacy.exists()
    legacy_empty = empty_workspace(legacy) if legacy_present else True
    if not destination_empty:
        require(not legacy_present or legacy_empty,
                'Both new and legacy kernel workspaces are populated; nothing was moved')
        prepared = validate_prepared(workspace, lock, lock_hash, validate_sources,
                                     allow_incomplete=allow_incomplete)
        action = 'existing'
    elif legacy_present and not legacy_empty:
        validate_prepared(legacy, lock, lock_hash, validate_sources)
        require(legacy.stat().st_dev == nearest_existing(workspace.parent).stat().st_dev,
                'Kernel workspace move crosses filesystems; no large copy was attempted')
        action, prepared = 'migrate', True
    else:
        require(not legacy_alias, 'Prepared legacy alias points to an empty workspace')
        action, prepared = 'fresh', False
    repair_alias = (action == 'existing' and prepared and legacy is not None
                    and not legacy_present and not legacy_alias)
    result = {'action': action, 'prepared': prepared, 'workspace': str(workspace),
              'legacy': str(legacy) if legacy is not None else None,
              'changed': action == 'migrate' or repair_alias or not (workspace / IGNORE_FILE).exists()}
    if not apply:
        return result
    if action != 'migrate':
        workspace.mkdir(parents=True, exist_ok=True)
        ignore = workspace / IGNORE_FILE
        add_ignore = not ignore.exists()
        if add_ignore:
            ignore.touch(exist_ok=False)
        if repair_alias:
            try:
                legacy.parent.mkdir(parents=True, exist_ok=True)
                legacy.symlink_to(os.path.relpath(workspace, legacy.parent), target_is_directory=True)
            except BaseException:
                if legacy.is_symlink() and os.readlink(legacy) == os.path.relpath(workspace, legacy.parent):
                    legacy.unlink()
                if add_ignore:
                    ignore.unlink()
                raise
        return result

    # The old directory and optional empty target are restored if alias creation
    # fails. Same-filesystem rename retains every source/cache/artifact inode.
    old_ignore = legacy / IGNORE_FILE
    created_ignore = not old_ignore.exists()
    target_existed = workspace.exists()
    target_mode = workspace.stat().st_mode & 0o7777 if target_existed else None
    target_ignore = workspace / IGNORE_FILE
    target_marker = target_ignore.read_bytes() if target_ignore.exists() else None
    target_marker_mode = target_ignore.stat().st_mode & 0o7777 if target_ignore.exists() else None
    moved = False
    removed_target = False
    ignore_added = False
    target_marker_removed = False
    try:
        if created_ignore:
            old_ignore.touch(exist_ok=False)
            ignore_added = True
        workspace.parent.mkdir(parents=True, exist_ok=True)
        if target_existed:
            if target_marker is not None:
                target_ignore.unlink()
                target_marker_removed = True
            workspace.rmdir()
            removed_target = True
        legacy.rename(workspace)
        moved = True
        legacy.symlink_to(os.path.relpath(workspace, legacy.parent), target_is_directory=True)
    except BaseException:
        if moved:
            if legacy.is_symlink() and os.readlink(legacy) == os.path.relpath(workspace, legacy.parent):
                legacy.unlink()
            # Do not overwrite a concurrently created legacy entry on rollback.
            require(not legacy.exists() and not legacy.is_symlink(),
                    'Migration rollback blocked by a new legacy entry; workspace retained at ' + str(workspace))
            workspace.rename(legacy)
        if ignore_added and old_ignore.exists():
            old_ignore.unlink()
        if removed_target:
            workspace.mkdir(mode=target_mode)
            workspace.chmod(target_mode)
            if target_marker is not None:
                target_ignore.write_bytes(target_marker)
                target_ignore.chmod(target_marker_mode)
        elif target_marker_removed:
            require(not target_ignore.exists() and not target_ignore.is_symlink(),
                    'Migration rollback marker conflicts with a new file: ' + str(target_ignore))
            target_ignore.write_bytes(target_marker)
            target_ignore.chmod(target_marker_mode)
        raise
    return result
