#!/usr/bin/env python3
"""Notify Telegram only after a validated upstream release has been published."""
import json
import os
from urllib import request, error


def message(upstream, commit):
    return ('✅ 腾讯视频 Egern 脚本已更新\n\n'
            f'上游版本：{upstream[:7]}\n'
            '构建与离线测试已通过，更新已发布。\n'
            '模块地址不变，在 Egern 刷新脚本即可。\n\n'
            f'更新记录：https://github.com/m20104600/AD/commit/{commit}')


def send(text, env=os.environ, opener=request.urlopen):
    credential = env.get('AD_TG_BOT_TOKEN', '')
    destination = env.get('AD_TG_CHAT_ID', '')
    if not credential or not destination:
        raise RuntimeError('Telegram notification secrets are not configured')
    data = json.dumps({'chat_id': destination, 'text': text,
                       'disable_web_page_preview': True}).encode()
    req = request.Request('https://api.telegram.org/bot' + credential + '/sendMessage',
                          data=data, headers={'Content-Type': 'application/json'})
    try:
        with opener(req, timeout=30) as response:
            result = json.load(response)
    except error.HTTPError as exc:
        raise RuntimeError('Telegram notification HTTP failure: ' + str(exc.code)) from None
    except Exception:
        raise RuntimeError('Telegram notification network failure') from None
    if not result.get('ok') or not result.get('result', {}).get('message_id'):
        raise RuntimeError('Telegram did not confirm the notification')
    print('Telegram accepted notification, message_id:', result['result']['message_id'])


if __name__ == '__main__':
    from pathlib import Path
    import subprocess
    meta = json.loads(Path('upstream/SOURCE.json').read_text())
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    send(message(meta['revision'], commit))
