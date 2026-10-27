#!/usr/bin/env python3
"""Stage a pinned upstream update; publish files only after offline validation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPO = 'ZenmoFeiShi/Qx'
FILES = ('TxvideoAD.snippet', 'Txvideoad.js')
OUTPUTS = ('upstream/TxvideoAD.snippet', 'upstream/Txvideoad.js',
           'upstream/SOURCE.json', 'scripts/txvideo-ad.egern.js')


def download(url):
    headers = {'User-Agent': 'AD-upstream-sync', 'Accept': 'application/vnd.github+json'}
    token = os.environ.get('GH_TOKEN')
    if token and url.startswith('https://api.github.com/'):
        headers['Authorization'] = 'Bearer ' + token
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=45) as response:
        data = response.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError('Upstream file exceeds 2 MB limit')
    return data


def functional_lines(data):
    return [line.strip() for line in data.decode('utf-8-sig').splitlines()
            if line.strip() and not line.lstrip().startswith(('#', ';', '//'))]


def validate_candidate(old_snippet, new_snippet, script):
    # Adapter URL dispatch and module mapping must be reviewed together.
    if functional_lines(old_snippet) != functional_lines(new_snippet):
        raise ValueError('Upstream rules changed; manual Egern rule/adapter review required')
    if not script.strip() or b'$done' not in script:
        raise ValueError('Upstream JS is empty or no longer a QX callback script')


def sync(root=ROOT, fetch=download, check=False):
    head = json.loads(fetch(f'https://api.github.com/repos/{REPO}/commits/main'))['sha']
    if not re.fullmatch(r'[0-9a-f]{40}', head):
        raise ValueError('Invalid upstream revision')
    # Both files are read at the same immutable revision, never two moving main URLs.
    candidate = {name: fetch(f'https://raw.githubusercontent.com/{REPO}/{head}/{name}')
                 for name in FILES}
    validate_candidate((root / 'upstream/TxvideoAD.snippet').read_bytes(),
                       candidate[FILES[0]], candidate[FILES[1]])
    changed = any((root / 'upstream' / name).read_bytes() != candidate[name] for name in FILES)
    if not changed:
        print('NO_CHANGE: upstream source files are unchanged')
        return False
    if check:
        print('UPDATE_AVAILABLE:', head)
        return True
    scratch = Path(os.environ.get('TMPDIR', str(Path.home() / '.cache/ad-sync')))
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ad-sync-', dir=scratch) as folder:
        stage = Path(folder) / 'repo'
        shutil.copytree(root, stage, ignore=shutil.ignore_patterns('.git', '.venv', '__pycache__', 'node_modules'))
        meta = json.loads((stage / 'upstream/SOURCE.json').read_text())
        meta['revision'] = head
        # Historical snippet_last_commit is not necessarily the new HEAD.
        meta.pop('snippet_last_commit', None)
        for name, data in candidate.items():
            (stage / 'upstream' / name).write_bytes(data)
            meta['files'][name] = {
                'url': f'https://raw.githubusercontent.com/{REPO}/{head}/{name}',
                'sha256': hashlib.sha256(data).hexdigest(),
            }
        (stage / 'upstream/SOURCE.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n')
        commands = [
            ['python3', 'tools/build.py'],
            ['node', '--check', 'scripts/txvideo-ad.egern.js'],
            ['node', '--test', *[str(p.relative_to(stage)) for p in sorted((stage / 'tests').glob('*.test.mjs'))]],
            ['python3', 'tests/validate_module.py'],
        ]
        for command in commands:
            subprocess.run(command, cwd=stage, check=True, timeout=120)
        for name in OUTPUTS:
            shutil.copy2(stage / name, root / name)
    print('UPDATED_AND_VALIDATED:', head)
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check without changing files')
    args = parser.parse_args()
    sync(check=args.check)
