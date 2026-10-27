import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sync_upstream', ROOT / 'tools/sync_upstream.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class SyncSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'upstream').mkdir()
        self.snippet = b'# title\nhttps://a/ url script-response-body https://a/test.js\n'
        self.script = b'$done({});\n'
        for name, data in zip(sync.FILES, (self.snippet, self.script)):
            (self.root / 'upstream' / name).write_bytes(data)
        (self.root / 'upstream/SOURCE.json').write_text(json.dumps({'files': {}}))
        self.sha = 'a' * 40
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        if '/commits/main' in url:
            return json.dumps({'sha': self.sha}).encode()
        return self.snippet if url.endswith('.snippet') else self.script

    def test_unchanged_upstream_does_not_write(self):
        before = (self.root / 'upstream/SOURCE.json').read_bytes()
        self.assertFalse(sync.sync(self.root, self.fetch))
        self.assertEqual((self.root / 'upstream/SOURCE.json').read_bytes(), before)
        self.assertTrue(all('/' + self.sha + '/' in u for u in self.calls[1:]))

    def test_rule_change_is_blocked_before_write(self):
        self.snippet += b'host, new.example, reject\n'
        with self.assertRaisesRegex(ValueError, 'manual Egern'):
            sync.sync(self.root, self.fetch)
        self.assertNotIn(b'new.example', (self.root / 'upstream/TxvideoAD.snippet').read_bytes())

    def test_check_mode_never_publishes(self):
        self.script = b'$done({body: "new"});\n'
        self.assertTrue(sync.sync(self.root, self.fetch, check=True))
        self.assertEqual((self.root / 'upstream/Txvideoad.js').read_bytes(), b'$done({});\n')

    def test_invalid_commit_is_rejected(self):
        self.sha = '../main'
        with self.assertRaisesRegex(ValueError, 'Invalid upstream'):
            sync.sync(self.root, self.fetch)

    def test_empty_script_is_rejected(self):
        self.script = b''
        with self.assertRaisesRegex(ValueError, 'empty'):
            sync.sync(self.root, self.fetch)

    def test_comments_do_not_change_rules(self):
        sync.validate_candidate(self.snippet, b'# new title\n' + self.snippet, self.script)

    def test_failed_build_leaves_all_release_files_untouched(self):
        self.script = b'$done({body:"new"});\n'
        before = {p.name: p.read_bytes() for p in (self.root / 'upstream').iterdir()}
        with patch.object(sync.subprocess, 'run', side_effect=RuntimeError('test build failure')):
            with self.assertRaisesRegex(RuntimeError, 'test build failure'):
                sync.sync(self.root, self.fetch)
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.root / 'upstream').iterdir()})

    def test_success_copies_only_validated_artifacts(self):
        self.script = b'$done({body:"new"});\n'
        def validated(command, cwd, **kwargs):
            target = cwd / 'scripts/txvideo-ad.egern.js'
            target.parent.mkdir(exist_ok=True)
            target.write_text('validated build')
        with patch.object(sync.subprocess, 'run', side_effect=validated) as run:
            (self.root / 'scripts').mkdir()
            self.assertTrue(sync.sync(self.root, self.fetch))
            self.assertEqual(run.call_count, 4)
        self.assertEqual((self.root / 'upstream/Txvideoad.js').read_bytes(), self.script)
        self.assertEqual((self.root / 'scripts/txvideo-ad.egern.js').read_text(), 'validated build')
        self.assertEqual(json.loads((self.root / 'upstream/SOURCE.json').read_text())['revision'], self.sha)


if __name__ == '__main__':
    unittest.main()
