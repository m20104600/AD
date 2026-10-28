import importlib.util
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sync_rate', ROOT / 'tools/sync_upstream.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class WorkflowAuthTests(unittest.TestCase):
    def test_resolver_is_read_only_and_authenticated_validation_has_no_token(self):
        jobs = yaml.safe_load((ROOT / '.github/workflows/sync-upstream.yml').read_text())['jobs']
        self.assertIn('resolve', jobs)
        resolver = jobs['resolve']
        self.assertEqual(resolver['permissions'], {'contents': 'read'})
        step = next(x for x in resolver['steps'] if '--resolve-only' in x.get('run', ''))
        self.assertEqual(step['env']['GH_TOKEN'], '${{ github.token }}')
        candidate = next(x for x in jobs['sync']['steps'] if 'python tools/sync_upstream.py' in x.get('run', ''))
        self.assertNotIn('GH_TOKEN', candidate.get('env', {}))
        self.assertIn('--revision', candidate['run'])
        self.assertEqual(jobs['sync']['needs'], 'resolve')


class DownloadRetryTests(unittest.TestCase):
    def test_429_waits_retry_after_before_retry(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'ok'
        error = HTTPError('https://api.github.com/test', 429, 'limited', {'Retry-After': '7'}, io.BytesIO(b''))
        with patch.object(sync.urllib.request, 'urlopen', side_effect=[error, response]) as request:
            with patch('time.sleep') as sleep:
                self.assertEqual(sync.download('https://api.github.com/test'), b'ok')
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(7)

    def test_long_quota_reset_defers_without_more_requests(self):
        error = HTTPError('https://api.github.com/test', 403, 'Forbidden',
                          {'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': '4600'}, io.BytesIO(b''))
        with patch.object(sync.urllib.request, 'urlopen', side_effect=error) as request:
            with patch('time.sleep') as sleep, patch('time.time', return_value=1000):
                with self.assertRaises(HTTPError):
                    sync.download('https://api.github.com/test')
        self.assertEqual(request.call_count, 1)
        sleep.assert_not_called()

    def test_non_rate_limit_403_is_not_retried(self):
        error = HTTPError('https://api.github.com/test', 403, 'Forbidden', {}, io.BytesIO(b''))
        with patch.object(sync.urllib.request, 'urlopen', side_effect=error) as request:
            with patch('time.sleep') as sleep:
                with self.assertRaises(HTTPError):
                    sync.download('https://api.github.com/test')
        self.assertEqual(request.call_count, 1)
        sleep.assert_not_called()

    def test_retries_are_bounded(self):
        error = HTTPError('https://api.github.com/test', 429, 'limited', {}, io.BytesIO(b''))
        with patch.object(sync.urllib.request, 'urlopen', side_effect=error) as request:
            with patch('time.sleep') as sleep:
                with self.assertRaises(HTTPError):
                    sync.download('https://api.github.com/test')
        self.assertEqual(request.call_count, 3)
        self.assertEqual([x.args[0] for x in sleep.call_args_list], [60, 60])

    def test_auth_only_goes_to_api_not_raw(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'ok'
        with patch.dict(os.environ, {'GH_TOKEN': 'offline-fixture-not-a-secret'}):
            with patch.object(sync.urllib.request, 'urlopen', return_value=response) as request:
                sync.download('https://api.github.com/repos/test/test')
                self.assertEqual(request.call_args.args[0].get_header('Authorization'), 'Bearer offline-fixture-not-a-secret')
                sync.download('https://raw.githubusercontent.com/test/test/main/a.js')
                self.assertIsNone(request.call_args.args[0].get_header('Authorization'))


if __name__ == '__main__':
    unittest.main()
