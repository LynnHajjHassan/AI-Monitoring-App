#!/usr/bin/env python3
"""Start camera-v1 simulator without printing credentials or putting them in argv."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from _local_env import read_env


def main():
    p = argparse.ArgumentParser(description='Run a local camera simulator using .env device token')
    p.add_argument('--env-file', default='.env')
    p.add_argument('--url', default='ws://127.0.0.1:8080/api/v1/ingest/ws')
    p.add_argument('--device-id', default='cam-01')
    p.add_argument('--fps', type=float, default=8)
    p.add_argument('--duration', type=float, default=20)
    args = p.parse_args()
    creds = json.loads(read_env(args.env_file)['CAMERA_DEVICE_TOKENS_JSON'])
    token = creds[args.device_id]
    env = dict(os.environ, SCENESENSE_CAMERA_TOKEN=token)
    target = Path(__file__).resolve().parents[1] / 'simulator' / 'sim_camera.py'
    cmd = [sys.executable, str(target), '--mode', 'ws', '--url', args.url, '--device-id', args.device_id,
           '--fps', str(args.fps), '--duration', str(args.duration)]
    return subprocess.call(cmd, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
