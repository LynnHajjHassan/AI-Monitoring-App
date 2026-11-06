# COMP4990 — Phase 2: MJPEG laptop bridge (additive patch)

## Verified input

- ESP32-S3 / OV5640 camera MJPEG: `http://192.168.2.160:81/api/v1/stream`
- User's 30.11-second benchmark: 144 frames, 4.78 observed FPS, 17.3 KiB average JPEG; 187 ms median inter-frame arrival, 328 ms p95, 1609 ms worst gap; 144 uptime stamps, 0 nonmonotonic.
- Existing snapshot upload bridge launch pattern: `python bridge/esp32_bridge.py --camera http://192.168.2.160 --server https://YOUR_FASTAPI_HOST --interval 1`.
- The existing FastAPI ingestion route, auth headers, POST request body, and exact Python source are **not present** in the accessible project files. **Do not blindly replace the existing uploader**; preserve its token and contract.

## Step 1: Back up existing working bridge

Windows PowerShell, repository root:

```powershell
Copy-Item .\bridge\esp32_bridge.py .\bridge\esp32_bridge.snapshot-backup.py
```

macOS/Linux:

```bash
cp bridge/esp32_bridge.py bridge/esp32_bridge.snapshot-backup.py
```

Copy `bridge/mjpeg_source.py` from this package into the repository's `bridge/` directory. No additional pip dependencies.

## Step 2: Verify MJPEG reader independent of uploader

```powershell
python tools/check_bridge_stream.py --camera http://192.168.2.160 --seconds 30
```

That output shows connected status, total observed frames, latest-frame age, and reconnection count.

**Important:** stop the existing browser MJPEG preview and benchmark before running this; the firmware currently permits only one MJPEG subscriber. Other frontend viewers will later connect to FastAPI, not to the ESP32 directly.

## Step 3: Replace only snapshot GET portion of `esp32_bridge.py`

This is an integration *pattern*, not an exact patch: the bridge's precise source is unavailable. Keep the CLI, `COMP4990_BRIDGE_TOKEN`, original upload path, original auth headers, and original POST logic unchanged.

At the top of the current bridge:

```python
from mjpeg_source import MJPEGCamera
import time
```

Where the existing code previously looped over `GET /api/v1/capture` and uploaded the bytes, replace the JPEG acquisition with this pattern:

```python
with MJPEGCamera(args.camera) as cam:
    last_sequence = 0
    last_upload_at = 0.0
    while True:
        frame = cam.wait_for_frame(last_sequence, timeout=3)
        if frame is None:
            print(f"No fresh camera frame: {cam.status()}")
            continue
        last_sequence = frame.sequence
        if time.monotonic() - last_upload_at < args.interval:
            continue  # discard preview frames; AI/backend upload stays at 1 fps

        jpeg_bytes = frame.jpeg
        device_uptime_us = frame.device_capture_uptime_us
        laptop_receive_utc = frame.received_utc

        # Existing authenticated POST logic goes here, unchanged:
        # use jpeg_bytes and, where supported, device_uptime_us metadata.
        # Do not create a new endpoint or rename payload fields.
        # upload_frame(jpeg_bytes, <your existing arguments>)

        last_upload_at = time.monotonic()
```

This is deliberately **not** a runnable replacement bridge until the original POST function is spliced in. Your working backend/frame contract must be preserved. Once patched, start it with the original command and environment variable for the bridge token.

## What improves now, and what does not

- ESP32 is read using **one persistent MJPEG connection**, rather than one GET per frame.
- Bridge only keeps the latest JPEG; **there is no growing queue of old frames**.
- Network reader runs in its own thread, so a slow HTTPS upload never blocks MJPEG acquisition. Upload jobs still execute sequentially.
- On disconnect or timeout, network reader reconnects with bounded backoff.
- The upstream backend still gets about **one sampled frame per second** until its contract is deliberately upgraded. The frontend does **not automatically become 4.8 FPS**.
- A future backend split will use a latest-frame preview path with a separate 30-second evidence sampler; it must not send all 4.8 FPS to the VLM.
- ESP32 uptime timestamps reset on reboot and are **not wall-clock timestamps**. `received_utc` is the laptop observation time, not actual sensor capture UTC.
- Camera read latency and backend rendering latency remain unmeasured.

## Phase 2 acceptance

1. Reader sees frames while the old bridge is stopped.
2. Existing bridge sends authenticated JPEGs to FastAPI after integrating the acquisition pattern.
3. Disconnect ESP32 Wi-Fi or power briefly; reader detects failure and reconnects when camera returns.
4. Frontend still receives valid frames after reconnect; check existing 30-second buffer does not include stale/corrupt entries.
5. Log device reboot, receiver sample age and server upload count; benchmark preview only after backend split.

## Mac portability

Only the Python 3.10+ standard library is used: `urllib`, `threading`, `dataclasses`, etc. Same camera URL and backend API; Mac terminal shell `export COMP4990_BRIDGE_TOKEN=...` instead of PowerShell `$env:COMP4990_BRIDGE_TOKEN=...`. A Mac must be on a network where it can reach the ESP32 and FastAPI. Physical testing on the teammate's Mac is still required.

**Security:** ESP32 HTTP MJPEG is appropriate only on a trusted local network. Preserve authenticated HTTPS for laptop-to-FastAPI. Do not put secrets into source code or print the bridge token.
