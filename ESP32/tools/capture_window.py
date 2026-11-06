"""Collect bounded ESP32 JPEG evidence using only the Python standard library."""
import argparse
from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.request import urlopen
from urllib.error import URLError


MAX_FRAME_BYTES = 2 * 1024 * 1024


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def read_frame(base_url, timeout=5):
    requested_at = utc_now()
    with urlopen(base_url.rstrip('/') + '/api/v1/capture', timeout=timeout) as response:
        if response.headers.get_content_type() != 'image/jpeg':
            raise ValueError('Camera did not return image/jpeg')
        data = response.read(MAX_FRAME_BYTES + 1)
        if len(data) > MAX_FRAME_BYTES:
            raise ValueError('Frame exceeds 2 MiB limit')
        if not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
            raise ValueError('Missing JPEG boundary markers')
        return data, {
            'request_started_at': requested_at,
            'received_at': utc_now(),
            'device_id': response.headers.get('X-Device-Id'),
            'capture_uptime_us': response.headers.get('X-Capture-Uptime-Us'),
        }


class RecentFrames:
    def __init__(self, window_seconds=30, max_frames=30):
        self.window_seconds = window_seconds
        self.frames = deque(maxlen=max_frames)

    def prune(self, now):
        while self.frames and now - self.frames[0][0] > self.window_seconds:
            self.frames.popleft()

    def add(self, now, data, metadata):
        self.prune(now)
        self.frames.append((now, data, metadata))

    def save(self, directory, now):
        self.prune(now)
        if not self.frames:
            raise ValueError('No recent frames available; nothing exported')
        directory.mkdir(parents=True, exist_ok=False)
        evidence = []
        for index, (_, data, metadata) in enumerate(self.frames):
            name = f'frame-{index:03d}.jpg'
            (directory / name).write_bytes(data)
            evidence.append(dict(metadata, file=name, bytes=len(data)))
        manifest = {
            'source_type': 'esp32',
            'evidence_type': 'sampled_frames',
            'frame_count': len(evidence),
            'time_window': {
                'start': evidence[0]['request_started_at'],
                'end': evidence[-1]['received_at'],
                'clock': 'laptop UTC request/receive bounds, not sensor exposure time',
            },
            'limitations': 'Sampled frames can miss brief events. Device uptime is not UTC. '
                            'JPEG markers are checked; full image decoding is not performed.',
            'frames': evidence,
        }
        (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('camera_url', help='e.g. http://192.168.1.50')
    parser.add_argument('--duration', type=float, default=30)
    parser.add_argument('--interval', type=float, default=1)
    parser.add_argument('--output', type=Path, default=Path('captures'))
    args = parser.parse_args()
    if not (0 < args.duration <= 3600 and 0.2 <= args.interval <= 30):
        parser.error('duration must be 0–3600 seconds and interval 0.2–30 seconds')
    if not args.camera_url.startswith(('http://', 'https://')):
        parser.error('camera_url must start with http:// or https://')
    buffer = RecentFrames()
    deadline = time.monotonic() + args.duration
    try:
        while time.monotonic() < deadline:
            started = time.monotonic()
            try:
                data, metadata = read_frame(args.camera_url)
                buffer.add(time.monotonic(), data, metadata)
                print(f'Captured {len(data)} bytes; {len(buffer.frames)} buffered')
            except (URLError, OSError, ValueError) as exc:
                buffer.prune(time.monotonic())
                print(f'Capture failed: {exc}')
            delay = min(args.interval - (time.monotonic() - started), deadline - time.monotonic())
            if delay > 0:
                time.sleep(delay)
    except KeyboardInterrupt:
        print('\nStopping capture and exporting recent evidence.')
    directory = args.output / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    try:
        manifest = buffer.save(directory, time.monotonic())
    except ValueError as exc:
        parser.exit(1, str(exc) + '\n')
    print(f'Saved {manifest["frame_count"]} frames and manifest to {directory.resolve()}')


if __name__ == '__main__':
    main()
