# COMP4990 Phase 3 — Additive FastAPI Camera v1 Integration

**Built against the Nov 6, 2026 `backup_backend` snapshot.** This is an **overlay patch**, not a replacement application and not firmware. Current deployed VM has **not** been changed by its creation.

## What changes

| File(s) | Change |
|---|---|
| `backend/app/main.py` | Includes `camera_v1` router; old routes untouched |
| `backend/camera_v1/` | Authenticated camera v1 WSS receiver, per-device latest image, 1 Hz sampled 30 s evidence |
| `backend/requirements.txt` | Adds the WebSocket protocol dependency to the container build |
| `backend/Dockerfile` | Copies new package and sets a bounded WebSocket message size; retains one worker |
| `compose.yaml` | Passes `CAMERA_DEVICE_TOKENS_JSON` and `CAMERA_VIEWER_TOKEN` with empty defaults; existing `BRIDGE_TOKEN` unchanged |
| `frontend/nginx.conf` | Adds explicit WebSocket Upgrade forwarding for `/api/v1/ingest/ws` |
| `backend/tests/` | Legacy compatibility tests and new camera integration tests |
| `simulator/` and `tools/` | Mac/Windows/Linux synthetic JPEG sender + safe local test helpers |
| `docs/` and `contract/` | Frozen v1 transport contract, OpenAPI and control schema |

**Scope/limitations:** The existing React UI **still reads the old** `/api/v1/sources/esp32` route. It will not show frames from the new WSS registry until a later UI integration. Likewise the existing AI Q&A route consumes legacy HTTP frames, not the new v1 evidence. This patch only integrates transport and device storage. Frigate is not part of COMP4990.

## Deploy (Linux application VM)

Follow [DEPLOY_WITH_ROLLBACK.md](docs/DEPLOY_WITH_ROLLBACK.md). From an extracted patch directory:

```bash
bash scripts/apply_patch.sh ~/comp4990-integration-starter
python3 scripts/generate_tokens.py ~/comp4990-integration-starter/.env
cd ~/comp4990-integration-starter
sudo docker compose config --quiet
sudo docker compose up -d --build backend frontend
sudo docker compose ps
```

**The installer checks SHA-256 hashes of six existing files against the uploaded backup, backs up the originals, and refuses to overwrite changed files.** If it stops, do not force-copy; review the conflicting file or send the live source for a merge.

Before deploying, run unit tests in a Python virtual environment as described in the deployment guide. Keep `.env` private and uncommitted. Do not send it to teammates. For macOS use the standalone Phase 2 package or copy the `simulator/` folder with fixtures; provide only one camera token through a secure channel.

## Public networking

Phase 3 test order is **loopback → Tailscale WSS → Cloudflare WSS**. Do **not** route your entire React/API app through a public tunnel as a shortcut; the old API has public GET routes without application login. See [CLOUDFLARE_NEXT.md](docs/CLOUDFLARE_NEXT.md) for a path-restricted ingress concept after the private test succeeds.

## Results achieved while preparing this package

- 12 FastAPI integration and legacy regression tests passed against the Nov 6 backup snapshot.
- Local `uvicorn + nginx + websockets` real-socket test succeeded: synthetic `cam-01` sent 24 frames at 8 FPS during a 3-second interval; backend sampled 3 evidence frames.
- Invalid auth, bad frame envelopes and independent device states are covered by unit tests.
- **Not tested here:** Docker Compose build on your VM, real Tailscale Serve WSS, Cloudflare, ESP32 firmware WSS, 30s AI path, high-FPS browser preview, actual Mac network access.
