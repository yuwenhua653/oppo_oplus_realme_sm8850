#!/usr/bin/env python3
"""Exercise a complete source snapshot, loss protection, and version checks."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / 'checkout'))
import publish
import build


class SourceTests(unittest.TestCase):
    def test_complete_source_snapshot_and_create_only(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source, remote = root / 'source', root / 'remote.git'
            source.mkdir()
            publish.git(source, 'init', '--quiet')
            publish.git(source, 'config', 'user.name', 'Source test')
            publish.git(source, 'config', 'user.email', 'test@example.invalid')
            for name, data in [('LICENSE', 'retained license\n'), ('old.c', 'old\n'), ('remove.c', 'remove\n')]:
                (source / name).write_text(data)
            publish.git(source, 'add', '--all')
            publish.git(source, 'commit', '--quiet', '-m', 'upstream')
            head = publish.git(source, 'rev-parse', 'HEAD')
            (source / 'old.c').write_text('adapted\n')
            (source / 'new.c').write_text('new driver\n')
            (source / 'remove.c').unlink()
            (source / 'private-log.txt').write_text('must not publish\n')
            publish.git(root, 'init', '--bare', '--quiet', str(remote))
            previous = publish.REPOSITORY
            publish.REPOSITORY = str(remote)
            try:
                row = {'head': head, 'files': [{'path': n} for n in ('old.c', 'new.c', 'remove.c')]}
                sha, tree = publish.snapshot_commit(source, row, 'myron/test', root / 'reports')
                self.assertEqual(set(publish.git(source, 'ls-tree', '--name-only', sha).splitlines()),
                                 {'LICENSE', 'old.c', 'new.c'})
                self.assertEqual(publish.git(source, 'show', sha + ':old.c'), 'adapted')
                self.assertEqual(publish.git(source, 'show', sha + ':LICENSE'), 'retained license')
                self.assertEqual(publish.git(source, 'rev-list', '--parents', '-n', '1', sha), sha)
                self.assertEqual(publish.snapshot_commit(source, row, 'myron/test', root / 'reports'), (sha, tree))
                (source / 'new.c').write_text('unreviewed\n')
                with self.assertRaisesRegex(ValueError, 'refusing replacement'):
                    publish.snapshot_commit(source, row, 'myron/test', root / 'reports')
                self.assertEqual(publish.git(remote, 'rev-parse', 'myron/test'), sha)
            finally:
                publish.REPOSITORY = previous

    def test_clean_release_only(self):
        head = 'a' * 40
        build.validate_release('6.12.81-android16-6-g' + head[:12] + '-4k', head)
        for version in ['6.12.81-android16-6-g' + head[:12] + '-dirty-4k',
                        '6.12.81-android16-6-maybe-4k', '6.12.81-android16-6-gbbbbbbbbbbbb-4k']:
            with self.assertRaises(ValueError):
                build.validate_release(version, head)

    def test_evidence_and_targets(self):
        rows = json.loads((HERE / 'r114-source-state.json').read_text())
        self.assertEqual({r['path'] for r in rows if r['files']}, set(publish.BRANCHES))
        self.assertEqual(sum(len(r['files']) for r in rows), 310)
        publish.compare_snapshot(rows, rows)
        with self.assertRaises(ValueError):
            publish.compare_snapshot(rows, rows[:-1])
        targets = json.loads((HERE / 'checkout/targets.json').read_text())
        self.assertEqual(len(targets), len(set(targets)))
        self.assertIn('//common:kernel_aarch64_modules', targets)
        self.assertTrue(any('focaltech_myron' in t for t in targets))


if __name__ == '__main__':
    unittest.main()
