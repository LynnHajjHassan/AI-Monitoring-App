# SceneSense / COMP4990 — Camera Protocol v1.0

**Status:** versioned implementation contract, frozen for Phase 2 local integration. Any incompatible wire change requires v2. **Scope:** ESP32-S3 camera or Python simulator → FastAPI ingest → latest-frame + separate sampled evidence. The existing `POST /api/v1/sources/esp32/frame` remains unchanged during migration. AI inference request/response format is intentionally outside this camera transport contract and will be agreed with the AI/UI developer.

## 1. Network and identity

- Camera initiates **outbound** TLS-verified **WSS** to `/api/v1/ingest/ws` on a reachable gateway. No port forwarding or gateway-to-camera route is required.
- Exceptions: `ws://localhost` or `ws://127.0.0.1` is allowed **only** for local development.
- Required WebSocket Upgrade request headers: `Authorization: Bearer <per-device-secret>` and `X-Device-Id: cam-01`. Camera IDs match `^[a-z][a-z0-9_-]{0,31}$`, max 32 characters.
- Authentication is validated **before** accepting the WebSocket. Server maps each ID to **its own** unique token (minimum 24 characters); a claim in `hello` alone is never trusted.
- Never put device tokens in URL query parameters, logs, source control or frontend code. HTTPS verifies the gateway's hostname and trusted CA; never disable verification.
- Initial deployment: one FastAPI worker with a memory-only registry. Sessions, frames, evidence and connection state do not survive process restarts. Multiworker / multi-instance support requires a shared state layer later.

## 2. Handshake

After HTTP Upgrade succeeds, camera sends **one JSON text frame** (strictly these 3 keys) within 5 seconds:

```json
{"type":"hello","version":1,"device_id":"cam-01"}
```

Server verifies ID equals the authenticated request header and replies:

```json
{
  "type": "ready", "version": 1, "device_id": "cam-01",
  "session_id": "74bb33cb-7b6d-4acb-b014-85c4d4f83010",
  "limits": {"max_jpeg_bytes": 1048576, "heartbeat_interval_seconds": 15}
}
```

`session_id` is a fresh server UUID per connection, not a camera-supplied identity. Camera sends binary images **only after** `ready`. Duplicate connections for the same camera **supersede** the older session. The old socket is closed with WebSocket code `4001`, and messages from the old session cannot overwrite the newer session's frames.

## 3. Binary JPEG envelope

Every image is **one binary WebSocket message**. Exactly **20 bytes of header** followed by the JPEG bytes. **Network/big-endian** unsigned integers throughout.

| Offset | Length | Type | Value |
| --- | ---: | --- | --- |
| 0 | 4 bytes | ASCII | `SCV1` (magic; identifies v1) |
| 4 | 1 byte | uint8 | `1` = JPEG frame |
| 5 | 1 byte | uint8 | flags = `0` (reserved) |
| 6 | 2 bytes | uint16 BE | reserved = `0` |
| 8 | 4 bytes | uint32 BE | `sequence`, starts at 1 per connection, strictly increasing |
| 12 | 8 bytes | uint64 BE | `capture_uptime_us`, monotonically nondecreasing within connection |
| 20 | 4–1,048,576 bytes | raw bytes | complete JPEG (`FF D8` ... `FF D9`) |

The server validates length, header, sequence and JPEG boundaries. Server uses its own UTC `received_at` plus monotonic arrival clock for buffering: the ESP32 uptime is **not UTC** and cannot be compared across reboots. A sequence wrap requires a new session; no wrap handling in v1. A JPEG's start/end bytes do **not** prove its pixel payload decodes; decoding validation can be added later with a resource limit.

**Example Python encoder:**

```python
import struct
payload = struct.pack('!4sBBHIQ', b'SCV1', 1, 0, 0, sequence, uptime_us) + jpeg
```

## 4. Heartbeats and disconnect

- Camera sends `{"type":"heartbeat"}` (JSON text message) at least every **15 seconds**. The server responds `{"type":"heartbeat_ack"}`. Data frames also prove activity; server considers 35 seconds with **no received messages** an idle timeout.
- WebSocket **control ping/pong** may also be used by the underlying library; not a substitute for the documented app heartbeat.
- No per-frame acknowledgement in v1: frame data is best-effort for preview, and an always-growing resend queue would increase latency. The WebSocket transport itself provides ordered reliable delivery while connected. After reconnect start sequence at 1 again.
- If send cannot keep up, camera should **skip superseded captures** rather than build an unbounded queue. A slow link can reduce delivered FPS without compromising evidence retention of accepted frames.
- State machine: `WIFI_DOWN → WIFI_CONNECTING → TLS_CONNECTING → AUTHENTICATING → STREAMING`, transitioning to `BACKOFF` on failures. Retry with exponential backoff and jitter, capped at 15 seconds. Keep the existing local `/health`, `/api/v1/capture` and port-81 `/api/v1/stream` routes for diagnostics. Don't tie local HTTP availability to public gateway success.
- Close codes: `1008` invalid authentication, handshake or binary frame; `1001` idle timeout; `4001` superseded device session; `1009` may be emitted by a proxy on oversized WebSocket messages. Invalid server configuration may produce `1011`.

## 5. Server-side storage, preview and evidence

A separate record exists for every authenticated camera (`cam-01`, `cam-02`, etc.). On each accepted binary image:

1. Atomically replace `latest` JPEG with the newest accepted frame — **no preview backlog**.
2. Independently add a JPEG to AI evidence only if at least **1 second** passed since the last sampled frame for that camera (the first frame of a session is always sampled).
3. Evidence expires after **30 seconds**, and is also capped to **30 frames / 6 MiB per camera**. Total retained evidence may cover less than 30 seconds when size limits require dropping old frames.
4. `connected=true` means the WebSocket session is active. `online=true` requires both a connected session and a JPEG received in the last **5 seconds**. `stale=true` means connected but not online. Frame age is measured at the server.
5. Server rejects sequence regression and capture uptime regression **within a session**, to avoid displaying old frames.

When the camera drops, latest preview returns `404` rather than displaying a stale frame as live. Evidence metadata can remain until its 30-second retention expires, but clients must not misrepresent stale evidence as live.

**Viewer API** (all require *separate* `Authorization: Bearer <viewer-token>`; cannot reuse device token):

- `GET /api/v1/devices` → `{ "devices": [DeviceStatus, ...] }`.
- `GET /api/v1/devices/{device_id}/status` → `DeviceStatus` or `404`.
- `GET /api/v1/devices/{device_id}/latest.jpg` → JPEG (with `Cache-Control: no-store`) or `404` when unavailable/stale.
- `GET /api/v1/devices/{device_id}/evidence` → timestamped **metadata only** (no JPEG data) for the currently retained evidence window.

See `contract/camera-v1.openapi.yaml` for response fields and status codes.

**Important browser security:** the viewer token must not be hard-coded into a publicly served React bundle. The development API is protected for curl/tests. When integrating React, place it behind an authenticated app backend (or use existing Tailscale access with a server-side viewer proxy). Browser WebSocket fanout and AI analysis will be separate follow-on contracts; they are **not** falsely claimed to exist in v1.

## 6. Configuration

- `CAMERA_DEVICE_TOKENS_JSON`: JSON mapping `device_id → secret`. Example mapping has placeholders, never actual credentials: `{"cam-01":"<long-unique-token>","cam-02":"<another-long-unique-token>"}`. At most 16 configured devices in this dev implementation.
- `CAMERA_VIEWER_TOKEN`: distinct viewer secret (minimum 24 characters).
- Existing `BRIDGE_TOKEN`, `INFERENCE_MODE` and HTTP fallback code remain unchanged.
- Test harness uses synthetic JPEGs; `simulator/sim_camera.py` offers WebSocket mode and legacy HTTP-upload mode.

## 7. Contract compatibility and acceptance

**Fixed in v1:** endpoint path, header auth and identity, hello/ready JSON, binary frame envelope layout and byte order, frame and evidence bounds, heartbeat names, API response keys, and disconnect semantics. Additive optional HTTP fields do not require v2; changes to required fields, frame layout or auth semantics do.

Minimum tests: bad tokens rejected, identity mismatch rejected, invalid JPEG/frame header rejected, monotonic ordering, separate camera state, fresh/stale status, evidence sampling distinct from preview, session supersession, network reconnect and macOS simulator interoperability. Local unit tests cover deterministic protocol behaviors; real Wi-Fi, TLS and Cloudflare reliability tests remain to be performed before deployment.
