#!/usr/bin/env python3
"""Validate module schema, exact QX route parity and reproducible embedding."""
import hashlib
import json
import re
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
module = yaml.safe_load((ROOT / 'modules/txvideo-ad.egern.yaml').read_text())
source = (ROOT / 'upstream/TxvideoAD.snippet').read_text()
assert all(module.get(k) for k in ('name', 'description', 'author', 'homepage'))
expected_domains = re.findall(r'^host,\s*([^,]+),\s*reject$', source, re.M)
actual_domains = []
for rule in module['rules']:
    assert set(rule) == {'domain'}
    assert rule['domain']['policy'] == 'REJECT'
    actual_domains.append(rule['domain']['match'])
assert actual_domains == expected_domains
source_hosts = re.search(r'^hostname = (.+)$', source, re.M).group(1).split(', ')
assert module['mitm']['hostnames'] == source_hosts
source_routes = re.findall(r'^(\S+) url script-(request|response)-body \S+$', source, re.M)
actual_routes = []
for entry in module['scriptings']:
    assert len(entry) == 1
    kind, body = next(iter(entry.items()))
    assert kind in ('http_request', 'http_response')
    assert body['body_required'] is True
    assert isinstance(body['binary_body'], bool)
    assert 0 < body['timeout'] <= 600
    assert body['max_size'] == 4194304
    assert body['update_interval'] == 3600
    assert body['script_url'] == 'https://raw.githubusercontent.com/m20104600/AD/main/scripts/txvideo-ad.egern.js'
    regex = body['match']
    rx = re.compile(regex)
    assert not rx.search('https://example.com/')
    assert not rx.search('https://i.video.qq.com.evil.test/')
    assert not rx.search('https://i.video.qq.com/not-a-root-route')
    actual_routes.append((regex, kind.removeprefix('http_')))
    is_json = 'rdelivery' in regex
    assert body['binary_body'] is not is_json
assert actual_routes == source_routes, (actual_routes, source_routes)
assert len(actual_routes) == 5

samples = [
    'https://i.video.qq.com/', 'http://i.video.qq.com/?a=1',
    'https://iacc.qq.com/?cmd=1',
    'https://config.ab.qq.com/tab/GetTabRemoteConfig?app=1',
    'https://rdelivery.qq.com/v1/sdkconfig/get?app=1',
]
for sample in samples:
    assert any(re.search(regex, sample) for regex, _ in actual_routes), sample
meta = json.loads((ROOT / 'upstream/SOURCE.json').read_text())
for name, info in meta['files'].items():
    assert hashlib.sha256((ROOT / 'upstream' / name).read_bytes()).hexdigest() == info['sha256']
original = (ROOT / 'upstream/Txvideoad.js').read_text()
output = (ROOT / 'scripts/txvideo-ad.egern.js').read_text()
expected = (ROOT / 'tools/egern-wrapper.js.txt').read_text().replace(
    '/*__UPSTREAM__*/', '// BEGIN UNCHANGED UPSTREAM\n' + original + '\n// END UNCHANGED UPSTREAM')
assert output == expected
assert 'ZenmoFeiShi/Qx' in (ROOT / 'README.md').read_text()
print('PASS: 2 reject rules, 4 MITM hosts, 5 exact route mappings, binary flags, pinned checksums and reproducible build')
