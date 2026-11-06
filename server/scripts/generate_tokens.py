#!/usr/bin/env python3
"""Append random camera-v1 secrets to an existing .env without revealing them.
Only generated values are in this local file. The legacy BRIDGE_TOKEN is preserved.
"""
import json
import os
import re
import secrets
import sys
import tempfile
from pathlib import Path


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else '.env').resolve()
    if len(sys.argv) > 2 or path.name != '.env':
        print('Usage: python3 scripts/generate_tokens.py /path/to/comp4990/.env', file=sys.stderr)
        return 2
    if path.exists() and path.is_symlink():
        print('Refusing to modify a symbolic link.', file=sys.stderr)
        return 2
    original = path.read_text() if path.exists() else ''
    for key in ('CAMERA_DEVICE_TOKENS_JSON', 'CAMERA_VIEWER_TOKEN'):
        if re.search(r'^\s*'+key+r'\s*=', original, re.MULTILINE):
            print(f'Refusing to overwrite existing {key}. No changes made.', file=sys.stderr)
            return 2
    credentials = {'cam-01': secrets.token_urlsafe(32), 'cam-02': secrets.token_urlsafe(32)}
    text = (original.rstrip('\n') + ('\n' if original else '') +
        '# SceneSense camera-v1 secrets (keep out of source control)\n'
        + 'CAMERA_DEVICE_TOKENS_JSON=\'' + json.dumps(credentials, separators=(',', ':')) + '\'\n'
        + 'CAMERA_VIEWER_TOKEN=' + secrets.token_urlsafe(32) + '\n')
    fd, temp = tempfile.mkstemp(prefix='.env.phase3-', dir=path.parent, text=True)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as out:
            out.write(text)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    os.chmod(path, 0o600)
    print(f'Wrote unique tokens for cam-01, cam-02 and a viewer into {path}. Tokens NOT printed.')
    print('Existing BRIDGE_TOKEN was preserved (if present). Never commit or upload .env.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
