#!/usr/bin/env python3
"""Check camera-v1 device states without putting viewer secrets in shell history."""
import argparse
import json
import sys
import urllib.request
from _local_env import read_env


def main():
    p = argparse.ArgumentParser(description='Query authorized per-camera status')
    p.add_argument('--env-file', default='.env')
    p.add_argument('--origin', default='http://127.0.0.1:8080')
    args = p.parse_args()
    if not (args.origin.startswith('https://') or args.origin.startswith('http://localhost:') or args.origin.startswith('http://127.0.0.1:')):
        p.error('Non-loopback device API origin must use HTTPS')
    token = read_env(args.env_file)['CAMERA_VIEWER_TOKEN']
    req = urllib.request.Request(args.origin.rstrip('/')+'/api/v1/devices', headers={'Authorization':'Bearer '+token})
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            print(json.dumps(json.load(res), indent=2))
        return 0
    except Exception as exc:
        print(f'Device-status request failed: {type(exc).__name__}: {exc}',file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
