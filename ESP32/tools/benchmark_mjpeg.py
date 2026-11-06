#!/usr/bin/env python3
"""Benchmark ESP32 MJPEG delivery with Python standard library only.

Examples (both Windows and macOS):
  python tools/benchmark_mjpeg.py http://192.168.1.50:81 --seconds 30
  python3 tools/benchmark_mjpeg.py http://192.168.1.50:81 --seconds 30 --json results.json

Measures observed receiver FPS, frame sizes, inter-frame arrival gaps and
first-frame time. This cannot determine true one-way latency without clock
synchronization between the ESP32 and the laptop.
"""

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MAX_JPEG_BYTES = 2_000_000


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = math.ceil(len(ordered) * fraction) - 1
    return ordered[max(0, min(index, len(ordered) - 1))]


def read_part(stream):
    # The HTTP library strips HTTP transfer-chunk framing for us; this parser
    # reads only MJPEG multipart delimiters, headers and JPEG body.
    for _ in range(20):
        line = stream.readline()
        if not line:
            raise EOFError("Stream ended while looking for JPEG boundary")
        if line.strip() == b"--frame":
            break
        if line.strip() == b"--frame--":
            raise EOFError("Stream ended normally")
    else:
        raise ValueError("No multipart --frame boundary found")

    headers = {}
    for _ in range(24):
        line = stream.readline()
        if not line:
            raise EOFError("Stream ended in part headers")
        if line in (b"\r\n", b"\n"):
            break
        if b":" not in line:
            raise ValueError("Malformed multipart header")
        key, value = line.split(b":", 1)
        headers[key.strip().lower().decode("ascii")] = value.strip().decode("ascii")
    else:
        raise ValueError("Too many multipart headers")

    n = int(headers.get("content-length", "0"))
    if not 4 <= n <= MAX_JPEG_BYTES:
        raise ValueError(f"Invalid or oversized Content-Length: {n}")
    data = stream.read(n)
    if len(data) != n:
        raise EOFError("Stream ended in JPEG body")
    if not (data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9")):
        raise ValueError("Multipart part did not contain a complete JPEG")
    return headers, len(data)


def run(base_url, seconds, json_path):
    url = base_url.rstrip("/")
    if not url.endswith("/api/v1/stream"):
        url += "/api/v1/stream"

    request = Request(url, headers={"User-Agent": "COMP4990-MJPEG-Benchmark/1.0"})
    started = time.monotonic()
    arrivals = []
    sizes = []
    timestamps_us = []
    print(f"Connecting to {url} for up to {seconds:g} seconds...")

    with urlopen(request, timeout=12) as stream:
        content_type = stream.headers.get("Content-Type", "")
        if "multipart/x-mixed-replace" not in content_type.lower():
            raise ValueError(f"Expected MJPEG multipart response, got {content_type!r}")
        while time.monotonic() - started < seconds:
            headers, size = read_part(stream)
            now = time.monotonic()
            arrivals.append(now)
            sizes.append(size)
            value = headers.get("x-capture-uptime-us")
            if value is not None:
                try:
                    timestamps_us.append(int(value))
                except ValueError:
                    pass
            if len(arrivals) % 20 == 0:
                elapsed = now - started
                print(f"  {len(arrivals)} frames in {elapsed:.1f}s")

    elapsed = time.monotonic() - started
    gaps_ms = [(b - a) * 1000 for a, b in zip(arrivals, arrivals[1:])]
    report = {
        "url": url,
        "elapsed_seconds": round(elapsed, 3),
        "frames": len(arrivals),
        "observed_fps": round(len(arrivals) / elapsed, 2) if elapsed else 0,
        "first_frame_ms": round((arrivals[0] - started) * 1000, 1) if arrivals else None,
        "average_jpeg_kib": round(statistics.mean(sizes) / 1024, 1) if sizes else None,
        "max_jpeg_kib": round(max(sizes) / 1024, 1) if sizes else None,
        "median_gap_ms": round(statistics.median(gaps_ms), 1) if gaps_ms else None,
        "p95_gap_ms": round(percentile(gaps_ms, 0.95), 1) if gaps_ms else None,
        "max_gap_ms": round(max(gaps_ms), 1) if gaps_ms else None,
        "device_timestamps_seen": len(timestamps_us),
        "device_timestamp_nonmonotonic": sum(
            b < a for a, b in zip(timestamps_us, timestamps_us[1:])
        ),
        "note": "Receiver delivery metrics only; true end-to-end latency not measured",
    }
    print("\n" + json.dumps(report, indent=2))
    if json_path:
        Path(json_path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Saved {json_path}")
    return 0 if arrivals else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="Example: http://192.168.1.50:81")
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--json", dest="json_path", help="Save metrics JSON")
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    try:
        return run(args.base_url, args.seconds, args.json_path)
    except KeyboardInterrupt:
        print("\nInterrupted")
        return 130
    except (HTTPError, URLError, OSError, EOFError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
