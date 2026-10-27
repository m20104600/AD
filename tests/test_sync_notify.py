import importlib.util
import io
import json
from pathlib import Path
import unittest
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('notify', ROOT / 'tools/notify_update.py')
notify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notify)


class NotificationTests(unittest.TestCase):
    def test_notification_payload(self):
        def mock_transport(req, timeout):
            payload = json.loads(req.data)
            self.assertEqual(payload['chat_id'], 'unit-test-chat')
            self.assertTrue(payload['disable_web_page_preview'])
            self.assertIn('abcdef0', payload['text'])
            self.assertNotIn('parse_mode', payload)
            return io.BytesIO(json.dumps({'ok': True, 'result': {'message_id': 1}}).encode())
        notify.send(notify.message('abcdef0123', 'a' * 40),
                    env={'AD_TG_BOT_TOKEN': 'unit-test-credential', 'AD_TG_CHAT_ID': 'unit-test-chat'},
                    opener=mock_transport)

    def test_missing_config_does_not_make_request(self):
        with self.assertRaisesRegex(RuntimeError, 'not configured'):
            notify.send('test', env={})

    def test_network_errors_do_not_leak_credential(self):
        def unavailable(req, timeout):
            raise URLError(req.full_url)
        with self.assertRaises(RuntimeError) as caught:
            notify.send('test', env={'AD_TG_BOT_TOKEN': 'unit-test-credential', 'AD_TG_CHAT_ID': 'unit-test-chat'}, opener=unavailable)
        self.assertNotIn('unit-test-credential', str(caught.exception))

    def test_no_change_skips_notification(self):
        import yaml
        data = yaml.safe_load((ROOT / '.github/workflows/sync-upstream.yml').read_text())
        steps = data['jobs']['sync']['steps']
        step = next(s for s in steps if s.get('name') == 'Notify Telegram after published update')
        self.assertEqual(step['if'], "steps.publish.outputs.updated == 'true'")
        self.assertTrue(step['continue-on-error'])
        publish = next(s for s in steps if s.get('id') == 'publish')['run']
        self.assertLess(publish.index('exit 0'), publish.index("echo 'updated=true'"))
        self.assertLess(publish.index('test "$local_sha" = "$remote_sha"'), publish.index("echo 'updated=true'"))
