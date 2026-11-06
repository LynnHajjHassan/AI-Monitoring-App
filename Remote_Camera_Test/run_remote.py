#!/usr/bin/env python3
"""Portable remote WSS test wrapper. Never requires a token in CLI arguments."""
import getpass
import os
import sys
from sim_camera import main

DEFAULT_WSS = "wss://comp4990.tail4a8541.ts.net/api/v1/ingest/ws"


def run():
    args = list(sys.argv[1:])
    if "--url" not in args:
        args += ["--url", DEFAULT_WSS]
    if "--device-id" not in args:
        args += ["--device-id", "cam-01"]
    if "--help" in args or "-h" in args:
        return main(args)
    original = os.environ.get("SCENESENSE_CAMERA_TOKEN")
    if not original:
        token = getpass.getpass("Device token (input hidden, never logged): ").strip()
        if len(token) < 24:
            print("Invalid token length. Nothing sent.", file=sys.stderr)
            return 2
        os.environ["SCENESENSE_CAMERA_TOKEN"] = token
    try:
        return main(args)
    except KeyboardInterrupt:
        print("\nTest stopped by operator.")
        return 130
    finally:
        if original is None:
            os.environ.pop("SCENESENSE_CAMERA_TOKEN", None)


if __name__ == "__main__":
    raise SystemExit(run())
