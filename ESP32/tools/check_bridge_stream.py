"""Smoke-test an MJPEG camera reader without changing the existing bridge."""
import argparse
import json
import logging
from pathlib import Path
import sys
import time

# Run from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge"))
from mjpeg_source import MJPEGCamera


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--camera", default="http://192.168.2.160", help="Camera base on port 80 OR :81 stream URL")
    p.add_argument("--seconds", type=float, default=30)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with MJPEGCamera(args.camera) as cam:
        end = time.monotonic() + args.seconds
        last_seq = 0
        frames = 0
        last_report = 0.0
        while time.monotonic() < end:
            frame = cam.wait_for_frame(last_seq, timeout=1.0)
            if frame:
                last_seq = frame.sequence
                frames += 1
            now = time.monotonic()
            if now - last_report >= 5:
                print(json.dumps({"frames_observed": frames, **cam.status()}, indent=2), flush=True)
                last_report = now
        status = cam.status()
        print("Final:", json.dumps(status, indent=2))
        return 0 if frames > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
