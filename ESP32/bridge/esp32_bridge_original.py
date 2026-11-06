#!/usr/bin/env python3
"""Simple laptop-side camera gateway: pull local ESP32 JPEG, push over HTTPS.

Only stdlib, no direct internet access by the ESP32, no secrets in source code.
One bridge per backend; keep the camera on your local Wi-Fi.
"""
import argparse
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MAX_JPEG_BYTES = 1024 * 1024


def read_frame(camera: str, timeout: float) -> tuple[bytes, dict[str, str]]:
    req = Request(camera.rstrip("/") + "/api/v1/capture", headers={"Cache-Control": "no-store"})
    with urlopen(req, timeout=timeout) as resp:
        if "image/jpeg" not in resp.headers.get("Content-Type", ""):
            raise ValueError("Camera endpoint did not return image/jpeg")
        frame = resp.read(MAX_JPEG_BYTES + 1)
        if len(frame) > MAX_JPEG_BYTES or not frame.startswith(b"\xff\xd8") or not frame.endswith(b"\xff\xd9"):
            raise ValueError("Invalid or oversized camera JPEG")
        headers = {
            "X-Device-Id": resp.headers.get("X-Device-Id", "esp32-s3"),
        }
        uptime = resp.headers.get("X-Capture-Uptime-Us")
        if uptime:
            headers["X-Capture-Uptime-Us"] = uptime
        return frame, headers


def push_frame(server: str, token: str, frame: bytes, camera_headers: dict[str, str], timeout: float) -> str:
    req = Request(
        server.rstrip("/") + "/api/v1/sources/esp32/frame", data=frame,
        headers={"Content-Type": "image/jpeg", "Authorization": "Bearer " + token, **camera_headers},
        method="POST",
    )
    with urlopen(req, timeout=timeout) as resp:
        if resp.status != 201:
            raise ValueError(f"Unexpected backend response {resp.status}")
        return resp.read(500).decode("utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser(description="ESP32 local-Wi-Fi to COMP4990 server bridge")
    parser.add_argument("--camera", required=True, help="Example: http://192.168.137.120")
    parser.add_argument("--server", required=True, help="HTTPS Tailscale Serve URL of your app")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between requests; default 1")
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--once", action="store_true", help="Send one frame and exit")
    args = parser.parse_args()
    token = os.environ.get("COMP4990_BRIDGE_TOKEN", "")
    if len(token) < 24:
        parser.error("Set COMP4990_BRIDGE_TOKEN to the same long random token as server BRIDGE_TOKEN")
    if not args.camera.startswith("http://") and not args.camera.startswith("https://"):
        parser.error("--camera must be an HTTP(S) URL")
    if not args.server.startswith("https://") and not (args.server.startswith("http://127.0.0.1:") or args.server.startswith("http://localhost:")):
        parser.error("--server requires HTTPS, except for local loopback testing")
    if args.interval < 0.5:
        parser.error("--interval must be at least 0.5 seconds")
    print(f"Camera: {args.camera} → server: {args.server}")
    print("Press Ctrl+C to stop. Upload token is never printed.")
    success = 0
    try:
        while True:
            start = time.monotonic()
            try:
                frame, headers = read_frame(args.camera, args.timeout)
                push_frame(args.server, token, frame, headers, args.timeout)
                success += 1
                print(f"[{time.strftime('%H:%M:%S')}] Sent frame #{success} ({len(frame)} bytes)")
                if args.once:
                    return 0
            except (HTTPError, URLError, ValueError, TimeoutError, OSError) as exc:
                print(f"[{time.strftime('%H:%M:%S')}] Capture/push failed: {exc}", file=sys.stderr)
                if args.once:
                    return 1
            time.sleep(max(0.0, args.interval - (time.monotonic() - start)))
    except KeyboardInterrupt:
        print("\nBridge stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
