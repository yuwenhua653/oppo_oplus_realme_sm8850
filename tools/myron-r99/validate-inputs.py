#!/usr/bin/env python3
"""Reject drift in public source pins before source synchronization."""
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def manifest():
    lock = json.loads((ROOT / 'source-lock.json').read_text())
    path = ROOT / 'resolved-manifest.xml'
    assert digest(path) == lock['resolved_manifest_sha256'], 'resolved manifest drift'
    tree = ET.parse(path).getroot()
    rows = []
    names = set()
    paths = set()
    for p in tree.findall('project'):
        name, location, revision = p.get('name'), p.get('path', p.get('name')), p.get('revision')
        assert name and location and re.fullmatch('[0-9a-f]{40}', revision or ''), 'unpinned project'
        assert name not in names and location not in paths, 'duplicate project'
        assert not PurePosixPath(location).is_absolute() and '..' not in PurePosixPath(location).parts
        names.add(name); paths.add(location)
        rows.append({'name': name, 'path': location, 'revision': revision})
    assert len(rows) == lock['project_count'] == 396
    assert next(r['revision'] for r in rows if r['path'] == 'system/core') == lock['system_core_commit']
    return rows

def main():
    rows = manifest()
    lock = json.loads((ROOT / 'source-lock.json').read_text())
    pins = [('selector/baseline/selinux.cpp', 'baseline_selinux_sha256'),
            ('selector/baseline/Android.bp', 'baseline_android_bp_sha256'),
            ('selector/recovery-only-permissive.patch', 'patch_sha256')]
    for path, key in pins:
        assert digest(ROOT / path) == lock[key], path + ' changed'
    assert lock['init_target'] == 'init_second_stage.recovery'
    assert not lock['private_runtime_uploaded'] and not lock['image_build_requested']
    forbidden = [p for p in ROOT.rglob('*') if p.is_file() and
                 (p.suffix in ('.ko', '.img', '.so', '.zip') or p.read_bytes()[:4] == b'\x7fELF')]
    assert not forbidden, 'private/runtime binary unexpectedly in source controls'
    print(json.dumps({'status':'PASS', 'pinned_projects':len(rows), 'target':lock['init_target']}))

if __name__ == '__main__':
    main()
