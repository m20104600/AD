#!/usr/bin/env python3
"""Offline deterministic build; validates the pinned upstream snapshot."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
meta = json.loads((ROOT / 'upstream/SOURCE.json').read_text())
for name, info in meta['files'].items():
    data = (ROOT / 'upstream' / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != info['sha256']:
        raise SystemExit('Upstream checksum mismatch: ' + name)
source = (ROOT / 'upstream/Txvideoad.js').read_text()
wrapper = (ROOT / 'tools/egern-wrapper.js.txt').read_text()
assert wrapper.count('/*__UPSTREAM__*/') == 1
output = wrapper.replace('/*__UPSTREAM__*/', '// BEGIN UNCHANGED UPSTREAM\n' + source + '\n// END UNCHANGED UPSTREAM')
path = ROOT / 'scripts/txvideo-ad.egern.js'
path.parent.mkdir(exist_ok=True)
path.write_text(output)
print('Built', path.relative_to(ROOT), len(output.encode()), 'bytes')
