#!/usr/bin/env python3
"""Portable simulated SceneSense ESP32 camera. Python 3.10+, Windows/macOS/Linux.

Supports old HTTP POST (immediate integration with existing React app) and the
new camera-v1 WebSocket protocol (local FastAPI v1 gateway + future firmware).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import struct
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    import websockets
except ImportError:
    websockets = None

MAGIC = b"SCV1"
HEADER = struct.Struct("!4sBBHIQ")
MAX_JPEG_BYTES = 1_048_576
DEFAULT_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def fixtures_from(path: Path) -> list[bytes]:
    files = sorted(path.glob("*.jpg")) + sorted(path.glob("*.jpeg"))
    if not files:
        raise ValueError(f"No JPEG images found in {path}")
    images = [f.read_bytes() for f in files]
    for image in images:
        if not (4 <= len(image) <= MAX_JPEG_BYTES and image[:2] == b"\xff\xd8" and image[-2:] == b"\xff\xd9"):
            raise ValueError("Fixture JPEG must be between 4 B and 1 MiB with JPEG markers")
    return images


def require_token(env_name: str) -> str:
    token = os.environ.get(env_name, "")
    if len(token) < 24:
        raise ValueError(f"Set {env_name} to a secret of at least 24 characters")
    return token


def http_mode(args, token: str, images: list[bytes]) -> int:
    if not (args.url.startswith("https://") or args.url.startswith("http://127.0.0.1:") or args.url.startswith("http://localhost:")):
        raise ValueError("HTTP destination must use HTTPS except local loopback testing")
    endpoint = args.url.rstrip("/") + "/api/v1/sources/esp32/frame"
    count = 0
    started = time.monotonic()
    next_tick = started
    while args.duration == 0 or (time.monotonic() - started) < args.duration:
        count += 1
        image = images[(count - 1) % len(images)]
        headers = {
            "Authorization": "Bearer " + token,
            "Content-Type": "image/jpeg",
            "X-Device-Id": args.device_id,
            "X-Capture-Uptime-Us": str(int((time.monotonic() - started) * 1_000_000)),
        }
        req = Request(endpoint, data=image, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=10) as response:
                if response.status != 201:
                    raise ValueError(f"Expected 201, received {response.status}")
            print(f"HTTP accepted #{count} device={args.device_id} bytes={len(image)}", flush=True)
        except (URLError, HTTPError, TimeoutError, ValueError) as exc:
            print(f"HTTP upload failed: {exc}", file=sys.stderr)
            return 1
        if args.once:
            break
        next_tick += 1.0 / args.fps
        time.sleep(max(0, next_tick - time.monotonic()))
        next_tick = max(next_tick, time.monotonic() - 1.0 / args.fps)
    return 0


async def heartbeat_loop(ws):
    while True:
        await asyncio.sleep(15)
        await ws.send(json.dumps({"type": "heartbeat"}))


async def control_receiver(ws):
    """Drain heartbeat ACKs; do not let long-running simulations build a receive queue."""
    async for message in ws:
        if isinstance(message, str):
            control = json.loads(message)
            if control != {"type": "heartbeat_ack"}:
                raise ValueError("Unexpected gateway control response")
        else:
            raise ValueError("Gateway sent unexpected binary payload")


async def ws_session(args, token: str, images: list[bytes], first_started: float) -> int:
    if websockets is None:
        raise ValueError("Install requirements.txt for WSS support: pip install -r requirements.txt")
    if not (args.url.startswith("wss://") or args.url.startswith("ws://127.0.0.1:") or args.url.startswith("ws://localhost:")):
        raise ValueError("WebSocket must use WSS except local loopback testing")
    print(f"Connecting camera {args.device_id} to {args.url}", flush=True)
    async with websockets.connect(
        args.url,
        additional_headers={"Authorization": "Bearer " + token, "X-Device-Id": args.device_id},
        open_timeout=10, close_timeout=3, max_size=4096,
        ping_interval=20, ping_timeout=20,
    ) as ws:
        await ws.send(json.dumps({"type": "hello", "version": 1, "device_id": args.device_id}))
        ready = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        if (ready.get("type"), ready.get("version"), ready.get("device_id")) != ("ready", 1, args.device_id):
            raise ValueError(f"Gateway did not accept hello: {ready.get('type')}")
        print(f"READY device={args.device_id} session={ready['session_id']}", flush=True)
        hb_task = asyncio.create_task(heartbeat_loop(ws))
        rx_task = asyncio.create_task(control_receiver(ws))
        sequence = 0
        interval = 1.0 / args.fps
        next_tick = time.monotonic()
        try:
            while args.duration == 0 or time.monotonic() - first_started < args.duration:
                sequence += 1
                if sequence >= 2**32:
                    raise ValueError("Sequence rollover requires a new session")
                image = images[(sequence - 1) % len(images)]
                uptime_us = int((time.monotonic() - first_started) * 1_000_000)
                payload = HEADER.pack(MAGIC, 1, 0, 0, sequence, uptime_us) + image
                await ws.send(payload)
                if sequence == 1 or sequence % max(1, round(args.fps * 5)) == 0:
                    print(f"WSS sent seq={sequence} bytes={len(image)}", flush=True)
                if args.once:
                    return sequence
                if args.drop_every and sequence >= args.drop_every:
                    print("Simulating network interruption (reconnect test)", flush=True)
                    return sequence
                next_tick += interval
                await asyncio.sleep(max(0, next_tick - time.monotonic()))
                next_tick = max(next_tick, time.monotonic() - interval)
        finally:
            hb_task.cancel()
            rx_task.cancel()
            await asyncio.gather(hb_task, rx_task, return_exceptions=True)
        return sequence


async def ws_mode(args, token: str, images: list[bytes]) -> int:
    started = time.monotonic()
    failures = 0
    while True:
        if args.duration and time.monotonic() - started >= args.duration:
            return 0
        try:
            await ws_session(args, token, images, started)
            if args.once or not args.drop_every:
                return 0
        except Exception as exc:
            # Authentication and malformed-protocol failures require a human fix, not a retry storm.
            if websockets is not None and isinstance(exc, websockets.exceptions.InvalidStatus) and exc.response.status_code in (401, 403):
                print("Camera authentication rejected; check ID and token", file=sys.stderr)
                return 1
            if websockets is not None and isinstance(exc, websockets.exceptions.ConnectionClosedError) and exc.rcvd and exc.rcvd.code in (1008, 1009):
                print("Camera frame/protocol rejected by gateway", file=sys.stderr)
                return 1
            print(f"Camera disconnected: {type(exc).__name__}: {exc}", file=sys.stderr)
            failures += 1
            if args.once or args.no_reconnect:
                return 1
        if args.no_reconnect:
            return 0
        delay = min(15.0, 2 ** min(failures, 4)) * random.uniform(0.8, 1.2)
        if args.duration and time.monotonic() + delay - started >= args.duration:
            return 0
        print(f"Reconnecting in {delay:.1f}s", flush=True)
        await asyncio.sleep(delay)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Simulate an ESP32 camera on Windows/macOS/Linux")
    parser.add_argument("--mode", choices=("ws", "http"), default="ws")
    parser.add_argument("--url", help="WSS ingest URL (ws) or existing FastAPI origin (http)")
    parser.add_argument("--device-id", default="cam-01")
    parser.add_argument("--token-env", help="Name of environment variable holding camera/bridge credential")
    parser.add_argument("--fps", type=float, default=8.0)
    parser.add_argument("--duration", type=float, default=30.0, help="Seconds, or 0 for indefinite")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--frames-dir", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--drop-every", type=int, default=0, help="WSS test: reconnect after N frames")
    parser.add_argument("--no-reconnect", action="store_true")
    args = parser.parse_args(argv)
    if not args.url:
        args.url = ("ws://127.0.0.1:8001/api/v1/ingest/ws" if args.mode == "ws" else "http://127.0.0.1:8000")
    if not args.token_env:
        args.token_env = ("SCENESENSE_CAMERA_TOKEN" if args.mode == "ws" else "COMP4990_BRIDGE_TOKEN")
    if not (0 < args.fps <= 30) or args.duration < 0 or args.drop_every < 0:
        parser.error("FPS must be 0-30; duration and drop-every must be nonnegative")
    if not args.device_id or len(args.device_id) > 32:
        parser.error("Invalid device ID")
    try:
        images = fixtures_from(args.frames_dir)
        token = require_token(args.token_env)
        print(f"{len(images)} synthetic fixtures | mode={args.mode} | fps={args.fps} | device={args.device_id}")
        if args.mode == "http":
            return http_mode(args, token, images)
        return asyncio.run(ws_mode(args, token, images))
    except (ValueError, KeyboardInterrupt) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
