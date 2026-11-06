# COMP4990 – Streaming upgrade, Phase 1 (ESP32 firmware + local benchmark)

**Scope:** ESP32-S3 + OV5640, PlatformIO/Arduino ESP32 firmware, Windows 11 and macOS clients. This is an additive module, **not** a replacement for the existing working application or its frontend. No Frigate components are involved.

## Comparison with teammate's legacy Arduino sketch

| Area | Legacy sketch | Working project / selected approach |
|---|---|---|
| GPIO map | OV5640 custom pins (XCLK15, SCCB 4/5, D0 11, D1 9, D2 8, D3 10, D4 12, D5 18, D6 17, D7 16, VSYNC6, HREF7, PCLK13) | Retain **existing** physical pin map |
| XCLK | 20 MHz | Preserve working value; 20 MHz is a reasonable starting point |
| Pixel format | `PIXFORMAT_JPEG` | JPEG |
| Initial resolution | QVGA, including explicit sensor override | VGA 640x480, if the working build is stable |
| JPEG quality | 12, then 10 if PSRAM found | Start at 12; lower number = better quality and larger JPEG |
| Framebuffer | 2 in PSRAM, latest grab mode if PSRAM | 2 PSRAM frames, `CAMERA_GRAB_LATEST` |
| No-PSRAM branch | Sets SVGA/DRAM but does not reset `fb_count` to 1 | Prefer fail-safe QVGA, 1 framebuffer if fallback is required |
| Orientation | `vflip=1`, `hmirror=0` | Preserve currently working `vflip=1`, `hmirror=1` |
| HTTP | `startCameraServer` defined elsewhere, from CameraWebServer example | Existing port-80 API remains; new stream service on port 81 |

**Note:** The teammate's source is incomplete by itself: it declares `startCameraServer()` but does not define it. The standard CameraWebServer source provides that implementation. Do not paste the old sketch over your current PlatformIO project.

## Install safely

1. Make a Git commit or copy of the working project first.
2. Copy `include/mjpeg_stream.h` into your **existing** PlatformIO `include/` directory.
3. Copy `src/mjpeg_stream.cpp` into your **existing** `src/` directory.
4. In the file containing your current `setup()`, add `#include "mjpeg_stream.h"` near the existing includes.
5. After **successful camera init, Wi-Fi connection, and existing port-80 API startup**, add:

   ```cpp
   if (!startMjpegServer()) {
     Serial.println("ERROR: MJPEG server did not start");
   }
   ```

   Keep the existing camera config, pin settings, handler registrations and Wi-Fi secrets where they currently live. Do **not** add a second `esp_camera_init()`.

6. **Important:** If your firmware already starts a separate stream HTTP server on port 81 (for example, the teammate's full CameraWebServer implementation), stop that duplicate server or select a different port. `mjpeg_stream.cpp` needs port 81 and control port 32769 free.
7. Build/upload using your existing PlatformIO environment:

   ```powershell
   pio run
   pio run -t upload --upload-port COM3
   pio device monitor --baud 115200
   ```

   Replace COM3 with the real Windows port. On macOS, upload via the actual `/dev/cu.*` device; the C++ source is the same. If `pio` is not on PATH, use the VS Code PlatformIO buttons.

## Verify the endpoints

- Existing: `http://CAMERA_IP/health`
- Existing: `http://CAMERA_IP/api/v1/status`
- Existing: `http://CAMERA_IP/api/v1/capture`
- **New**: `http://CAMERA_IP:81/api/v1/stream`

The new endpoint returns an HTTP `multipart/x-mixed-replace` response with JPEG parts and `Content-Length` plus per-part `X-Capture-Uptime-Us`. Device capture time is boot-relative, **not UTC**. The first three endpoints are intentionally left untouched.

Use **one** ESP32 stream consumer: the laptop bridge. Avoid opening multiple camera streams in separate browser tabs. The new code returns HTTP 503 to additional simultaneous stream clients. A client disconnect releases the slot, so it can reconnect. For test purposes, a direct browser tab pointed at the stream URL can show moving MJPEG images; close it before benchmarking.

## Benchmark (no dependencies)

From the root of the package / project containing `tools/benchmark_mjpeg.py`:

```powershell
# Windows PowerShell
python tools/benchmark_mjpeg.py http://CAMERA_IP:81 --seconds 30 --json benchmark_windows.json
```

```bash
# macOS Terminal
python3 tools/benchmark_mjpeg.py http://CAMERA_IP:81 --seconds 30 --json benchmark_mac.json
```

Record: observed FPS, first-frame time, mean/max JPEG size, median/p95/max gap, disconnects/reconnects, and upright/mirrored orientation. Test with the camera stationary, then with motion and Wi-Fi signal fluctuations. Repeat for 60 seconds after the 30-second baseline.

**Latency caution:** receiver FPS and first-frame time are measurable from a single host; true one-way camera-to-laptop latency requires synchronized clock measurements or a visual reference such as a stopwatch/LED time source. A device uptime timestamp should not be subtracted directly from a laptop wall-clock timestamp.

## Acceptance / regression checks

- [ ] Existing `/health` still returns HTTP 200
- [ ] Existing `/api/v1/status` JSON unchanged
- [ ] Existing `/api/v1/capture` returns a valid upright JPEG
- [ ] `/api/v1/stream` streams JPEGs over one persistent connection
- [ ] 30–60 second local benchmark has zero JPEG parse errors
- [ ] Disconnect/reconnect the stream client repeatedly without rebooting camera
- [ ] Verify PSRAM present and orientation is correct
- [ ] Do **not** modify the laptop bridge or FastAPI endpoint yet

## Next step after firmware tests

Upgrade `bridge/esp32_bridge.py` to consume one MJPEG HTTP response, use a bounded reconnect/backoff loop, and publish the most recent JPEG immediately. Then split the backend's live-preview and AI evidence pathways: preview buffer stores only the newest frame, while evidence stores a separately sampled 30-second window. The 30-second AI buffer belongs on the laptop/backend, **not** the microcontroller; increasing the ESP32 framebuffer count makes streaming more memory-intensive and does not provide a correctly timestamped evidence window.

Do not add browser webcam or MP4 ingestion back; the ESP32 is the sole active camera source. GPU VLM integration follows after baseline capture stability.
