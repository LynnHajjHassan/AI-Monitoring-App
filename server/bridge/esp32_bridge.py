#!/usr/bin/env python3
"""COMP4990 laptop camera gateway: ESP32 MJPEG -> existing HTTPS FastAPI JPEG upload.

The ESP32 camera stays on local Wi-Fi. A single background reader consumes the
MJPEG stream and exposes only the newest JPEG; this bridge samples that frame
for the existing authenticated upload route. Preview streaming is a separate,
future backend change. Python 3.10+, standard library only; Windows/macOS.
"""

import argparse
import logging
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from mjpeg_source import MJPEGCamera, stream_url

MAX_JPEG_BYTES = 1024 * 1024
LOG = logging.getLogger(__name__)


def read_frame(camera: str, timeout: float) -> tuple[bytes, dict[str, str]]:
    """Original snapshot reader, retained for --mode snapshot rollback."""
    req = Request(camera.rstrip("/") + "/api/v1/capture", headers={"Cache-Control": "no-store"})
    with urlopen(req, timeout=timeout) as resp:
        if "image/jpeg" not in resp.headers.get("Content-Type", ""):
            raise ValueError("Camera endpoint did not return image/jpeg")
        frame = resp.read(MAX_JPEG_BYTES + 1)
        if len(frame) > MAX_JPEG_BYTES or not frame.startswith(b"\xff\xd8") or not frame.endswith(b"\xff\xd9"):
            raise ValueError("Invalid or oversized camera JPEG")
        headers = {"X-Device-Id": resp.headers.get("X-Device-Id", "esp32-s3")}
        uptime = resp.headers.get("X-Capture-Uptime-Us")
        if uptime:
            headers["X-Capture-Uptime-Us"] = uptime
        return frame, headers


def push_frame(server: str, token: str, frame: bytes, camera_headers: dict[str, str], timeout: float) -> str:
    """UNCHANGED backend contract: raw JPEG, Bearer token, 201 Created."""
    req = Request(
        server.rstrip("/") + "/api/v1/sources/esp32/frame", data=frame,
        headers={"Content-Type": "image/jpeg", "Authorization": "Bearer " + token, **camera_headers},
        method="POST",
    )
    with urlopen(req, timeout=timeout) as resp:
        if resp.status != 201:
            raise ValueError(f"Unexpected backend response {resp.status}")
        return resp.read(500).decode("utf-8", errors="replace")


def run_snapshot(args: argparse.Namespace, token: str) -> int:
    """Old behavior, unchanged; useful for rollback/diagnosis."""
    success = 0
    while True:
        start = time.monotonic()
        try:
            frame, headers = read_frame(args.camera, args.timeout)
            push_frame(args.server, token, frame, headers, args.timeout)
            success += 1
            print(f"[{time.strftime('%H:%M:%S')}] Sent snapshot #{success} ({len(frame)} bytes)")
            if args.once:
                return 0
        except (HTTPError, URLError, ValueError, TimeoutError, OSError) as exc:
            print(f"[{time.strftime('%H:%M:%S')}] Capture/push failed: {exc}", file=sys.stderr)
            if args.once:
                return 1
        time.sleep(max(0.0, args.interval - (time.monotonic() - start)))


def run_mjpeg(args: argparse.Namespace, token: str) -> int:
    """One continuous camera connection, but sample latest frames for existing POST.

    Uploading is deliberately independent of camera reception: a slow POST
    cannot accumulate old MJPEG frames. Newer frames replace older frames in
    MJPEGCamera's single-slot buffer.
    """
    success = 0
    last_sequence = 0
    next_upload_at = 0.0
    last_notice = 0.0
    with MJPEGCamera(args.camera, timeout_seconds=args.timeout,
                     stale_after_seconds=args.stale_after) as camera:
        print(f"MJPEG source: {camera.url}", flush=True)
        while True:
            frame = camera.wait_for_frame(after_sequence=last_sequence,
                                          timeout=(args.timeout if args.once else min(3.0, args.timeout)))
            if frame is None:
                # 'once' must be finite and report a failed first-frame attempt.
                if args.once:
                    print("No fresh MJPEG frame arrived before timeout", file=sys.stderr)
                    return 1
                now = time.monotonic()
                if now - last_notice >= 5.0:
                    state = camera.status()
                    print(f"[{time.strftime('%H:%M:%S')}] Waiting for camera; "
                          f"connected={state['connected']} last_error={state['last_error']}",
                          file=sys.stderr)
                    last_notice = now
                continue

            # Don't upload a frame twice. The reader may have skipped intermediate
            # sequences while a prior POST blocked; this is intentional.
            last_sequence = frame.sequence
            started = time.monotonic()
            if started < next_upload_at:
                continue
            # Preserve prior ingestion headers. The MJPEG part has device uptime
            # but no device-ID header, so explicitly use the same original fallback.
            headers = {"X-Device-Id": args.device_id}
            if frame.device_capture_uptime_us is not None:
                headers["X-Capture-Uptime-Us"] = str(frame.device_capture_uptime_us)

            # Limit each upstream payload to the old snapshot size/format.
            # A 2 MiB transport limit exists in MJPEGCamera but FastAPI's
            # existing endpoint was designed around <=1 MiB JPEGs.
            if len(frame.jpeg) > MAX_JPEG_BYTES:
                print(f"[{time.strftime('%H:%M:%S')}] Skipping oversized JPEG "
                      f"({len(frame.jpeg)} bytes)", file=sys.stderr)
                next_upload_at = started + args.interval
                continue
            try:
                push_frame(args.server, token, frame.jpeg, headers, args.timeout)
                success += 1
                print(f"[{time.strftime('%H:%M:%S')}] Sent frame #{success}: "
                      f"sequence={frame.sequence} bytes={len(frame.jpeg)} "
                      f"age_at_upload={frame.age_ms:.0f}ms", flush=True)
                if args.once:
                    return 0
            except (HTTPError, URLError, ValueError, TimeoutError, OSError) as exc:
                print(f"[{time.strftime('%H:%M:%S')}] Upload failed: {exc}", file=sys.stderr)
                if args.once:
                    return 1

            # Interval measures upload START-to-START, rather than adding upload
            # duration to each cycle; if upload is slow, simply send next fresh
            # frame without attempting to catch up on missed slots.
            next_upload_at = started + args.interval


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ESP32 local-Wi-Fi to COMP4990 server bridge")
    parser.add_argument("--camera", required=True, help="Example: http://192.168.137.120")
    parser.add_argument("--server", required=True, help="HTTPS Tailscale Serve URL of your app")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="Seconds between backend upload starts; default 1")
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--once", action="store_true", help="Send one frame and exit")
    parser.add_argument("--mode", choices=("mjpeg", "snapshot"), default="mjpeg",
                        help="MJPEG is default; snapshot restores old polling")
    parser.add_argument("--device-id", default="esp32-s3",
                        help="Device-ID for MJPEG upload (stream has no ID header)")
    parser.add_argument("--stale-after", type=float, default=2.0,
                        help="Reject MJPEG frames older than this many seconds")
    args = parser.parse_args(argv)
    token = os.environ.get("COMP4990_BRIDGE_TOKEN", "")
    if len(token) < 24:
        parser.error("Set COMP4990_BRIDGE_TOKEN to the same long random token as server BRIDGE_TOKEN")
    if not args.camera.startswith("http://") and not args.camera.startswith("https://"):
        parser.error("--camera must be an HTTP(S) URL")
    if not args.server.startswith("https://") and not (args.server.startswith("http://127.0.0.1:") or args.server.startswith("http://localhost:")):
        parser.error("--server requires HTTPS, except for local loopback testing")
    if args.interval < 0.5:
        parser.error("--interval must be at least 0.5 seconds")
    if args.timeout <= 0 or args.stale_after <= 0:
        parser.error("--timeout and --stale-after must be positive")
    if not args.device_id or any(c in args.device_id for c in "\r\n"):
        parser.error("--device-id must be non-empty and cannot contain line breaks")
    if args.mode == "mjpeg":
        try:
            stream_url(args.camera)  # fail before starting the worker
        except ValueError as exc:
            parser.error(str(exc))
    print(f"Camera: {args.camera} -> server: {args.server} (mode={args.mode})")
    print("Press Ctrl+C to stop. Upload token is never printed.")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        if args.mode == "snapshot":
            return run_snapshot(args, token)
        return run_mjpeg(args, token)
    except KeyboardInterrupt:
        print("\nBridge stopped")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
