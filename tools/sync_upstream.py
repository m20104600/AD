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
import urllib.error
import time
import sys
from email.utils import parsedate_to_datetime

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
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=45) as response:
                data = response.read(2_000_001)
            if len(data) > 2_000_000:
                raise ValueError('Upstream file exceeds 2 MB limit')
            return data
        except urllib.error.HTTPError as exc:
            rate_limited = exc.code == 429 or (exc.code == 403 and (
                exc.headers.get('X-RateLimit-Remaining') == '0'
                or exc.headers.get('Retry-After') is not None
                or 'rate limit' in str(exc.reason).lower()))
            if not rate_limited and exc.code not in (500, 502, 503, 504):
                raise
            if attempt == 2:
                raise
            delay = 60 if rate_limited else 5 * (2 ** attempt)
            retry_after = exc.headers.get('Retry-After')
            if retry_after:
                try:
                    delay = float(retry_after)
                except ValueError:
                    delay = parsedate_to_datetime(retry_after).timestamp() - time.time()
            elif exc.headers.get('X-RateLimit-Remaining') == '0' and exc.headers.get('X-RateLimit-Reset'):
                delay = float(exc.headers['X-RateLimit-Reset']) - time.time() + 1
            # Never hammer a depleted quota; leave the current release intact until next schedule.
            if delay > 60:
                print('GitHub quota unavailable for over 60s; deferring to next scheduled run.', file=sys.stderr)
                raise
            delay = max(1, delay)
            exc.close()
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
            delay = 5 * (2 ** attempt)
        print(f'Upstream fetch retry {attempt + 1}/2 after {delay:g}s.', file=sys.stderr)
        time.sleep(delay)


def functional_lines(data):
    return [line.strip() for line in data.decode('utf-8-sig').splitlines()
            if line.strip() and not line.lstrip().startswith(('#', ';', '//'))]


def validate_candidate(old_snippet, new_snippet, script):
    # Adapter URL dispatch and module mapping must be reviewed together.
    if functional_lines(old_snippet) != functional_lines(new_snippet):
        raise ValueError('Upstream rules changed; manual Egern rule/adapter review required')
    if not script.strip() or b'$done' not in script:
        raise ValueError('Upstream JS is empty or no longer a QX callback script')


def resolve_revision(fetch=download):
    head = json.loads(fetch(f'https://api.github.com/repos/{REPO}/commits/main'))['sha']
    if not isinstance(head, str) or not re.fullmatch(r'[0-9a-f]{40}', head):
        raise ValueError('Invalid upstream revision')
    return head


def sync(root=ROOT, fetch=download, check=False, revision=None):
    head = resolve_revision(fetch) if revision is None else revision
    if not isinstance(head, str) or not re.fullmatch(r'[0-9a-f]{40}', head):
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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--resolve-only', action='store_true', help='Resolve HEAD using read-only API authentication')
    mode.add_argument('--revision', help='Use a pinned SHA without querying the API')
    args = parser.parse_args()
    if args.resolve_only:
        print(resolve_revision())
    else:
        sync(check=args.check, revision=args.revision)
