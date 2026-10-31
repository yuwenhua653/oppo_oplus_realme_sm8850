#!/usr/bin/env python3
"""Exercise the actual archived R13 input migration, including drift rejection."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import subprocess
import dt_source_bridge as b

REPO = Path(__file__).resolve().parents[1]

class Migration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        shutil.copy2(REPO / 'myron-boot-r18.zip', self.repo)
        self.original = b.originals(self.repo)
        for name, data in self.original.items():
            p = self.repo / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)

    def test_only_dt_project_and_declared_revision_guards_change(self):
        digest = b.migrate(self.repo)
        self.assertEqual(digest, b.migrate(self.repo, verify=True))
        before = json.loads(self.original['myron-qcom-platform-r1/sources.lock.json'])
        after = json.loads((self.repo / 'myron-qcom-platform-r1/sources.lock.json').read_bytes())
        changes = [(x, y) for x, y in zip(before['projects'], after['projects']) if x != y]
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0][0]['path'], b.DT)
        self.assertEqual(changes[0][1], dict(changes[0][0], commit=b.NEW))
        lock = json.loads((self.repo / 'myron-adaptation-r12/bundle-lock.json').read_bytes())
        for row in lock['files']:
            self.assertEqual(b.sha((self.repo / 'myron-adaptation-r12' / row['path']).read_bytes()), row['sha256'])
        _, edits = b.expected_edits(self.repo)
        self.assertEqual(len(edits), 5)
        for name, data in self.original.items():
            if name not in edits:
                self.assertEqual((self.repo / name).read_bytes(), data)

    def test_reject_changed_guard_and_lock(self):
        b.migrate(self.repo)
        p = self.repo / 'myron-adaptation-r12/dt/validate_dt.py'
        p.write_bytes(p.read_bytes() + b'\n# unreviewed change\n')
        with self.assertRaises(ValueError):
            b.migrate(self.repo, verify=True)

    def test_verify_rejects_unmigrated_package(self):
        with self.assertRaises(ValueError):
            b.migrate(self.repo, verify=True)

    def test_real_collection_helper_accepts_migrated_manifest(self):
        shutil.copytree(REPO/'r55-source/ci',self.repo/'r55-source/ci')
        b.migrate(self.repo)
        workspace=self.repo/'workspace'
        actual_run=subprocess.run
        def run(args, **kwargs):
            data=kwargs.get('input',b'')
            if b'# Exact shell body from the pinned R18 workflow step: Fix Myron DTBO output collection' in data:
                return actual_run(args,**kwargs)
            return subprocess.CompletedProcess(args,0)
        with patch.object(b.subprocess,'run',side_effect=run):
            b.legacy(self.repo,workspace)
        _,edits=b.expected_edits(self.repo)
        expected=b.collection_manifest(edits[b.DT_MANIFEST])
        self.assertEqual((self.repo/b.DT_MANIFEST).read_bytes(),expected)
        b.migrate(self.repo,verify=True)
        b.migrate(self.repo)
        self.assertEqual((self.repo/b.DT_MANIFEST).read_bytes(),expected)

    def test_boundary_keeps_original_contract_and_other_guards(self):
        b.migrate(self.repo)
        class Parent:
            def __init__(self, repo): self.contract = {'sources_lock_sha256': b.OLD_LOCK, 'driver_gate': True}
            def check(self, repo): return self.contract, 'unchanged'
        boundary = b.boundary(Parent, self.repo)
        contract, other = boundary.check(self.repo)
        self.assertEqual(contract['sources_lock_sha256'], b.migrate(self.repo, verify=True))
        self.assertTrue(contract['driver_gate'])
        self.assertEqual(other, 'unchanged')
        self.assertEqual(boundary.contract['sources_lock_sha256'], b.OLD_LOCK)
        boundary.contract['sources_lock_sha256'] = 'unexpected'
        with self.assertRaises(ValueError): boundary.check(self.repo)

if __name__ == '__main__':
    unittest.main(verbosity=2)
