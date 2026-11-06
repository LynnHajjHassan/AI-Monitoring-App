# Deploy SceneSense Camera v1 into the existing COMP4990 VM

**Goal:** keep the known-working ESP32 -> MJPEG -> Windows HTTP bridge -> FastAPI -> React flow intact, while adding a separate authenticated multi-camera WebSocket ingest path. No AI model or firmware change is required for these steps.

## 0. Get patch onto the application VM

Copy `COMP4990_Phase3_Integration_Patch.zip` from Windows to the application VM with your preferred SSH/SCP or secure file transfer method. Example (replace `YOUR_SSH_HOST` with the VM SSH/Tailscale address):

```powershell
scp .\COMP4990_Phase3_Integration_Patch.zip marco@YOUR_SSH_HOST:~/
```

On the VM:

```bash
cd ~
unzip -q COMP4990_Phase3_Integration_Patch.zip
cd COMP4990_Phase3_Integration_Patch
```

If the repo is not `~/comp4990-integration-starter`, substitute your actual repo path in the steps below.

## 1. Backup and overlay (guarded)

```bash
bash scripts/apply_patch.sh ~/comp4990-integration-starter
```

The installer checks SHA-256 hashes for `backend/app/main.py`, `backend/Dockerfile`, `backend/requirements.txt`, `backend/tests/test_api.py`, `frontend/nginx.conf` and `compose.yaml` against the uploaded Nov 6 snapshot. **On mismatch it refuses before changing anything.** Do not force overwrite newer live source files. The script records a backup tar under `~/comp4990-backups/phase3-<UTC-timestamp>/` and prints the exact path. Save it for rollback. The script does **not** restart containers or modify `.env`.

## 2. Generate secure per-camera credentials (once)

```bash
python3 scripts/generate_tokens.py ~/comp4990-integration-starter/.env
```

This adds random `cam-01`, `cam-02` and viewer tokens to `.env` with restricted file permissions, preserving the existing `BRIDGE_TOKEN`. It will refuse to overwrite existing camera token settings. **The secrets are never printed**. Do not commit `.env`, paste tokens into ChatGPT, bake credentials into the firmware repository, or give your teammate the full `.env`. Exchange only their camera's token securely when needed.

The existing `BRIDGE_TOKEN` must still be configured as before. Compose interpolates these variables into the backend service at startup. Device and viewer tokens are separate; neither can replace the other.

## 3. Verify Python tests and Compose config before restarting

```bash
cd ~/comp4990-integration-starter
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
PYTHONPATH=backend python -m pytest backend/tests -q
sudo docker compose config --quiet
deactivate
```

Expected backend tests: **12 passed** for the uploaded snapshot plus patch. If the server's repository has different tests, their total may differ. No source/containers should be deployed if tests fail. `python3-venv` may be required on Debian/Ubuntu. This test does not install the simulator's optional `websockets` dependency yet.

## 4. Rebuild only the backend and unchanged frontend proxy image

```bash
sudo docker compose up -d --build backend frontend
sudo docker compose ps
sudo docker compose logs --since=2m --tail=50 backend frontend
```

The original frontend code is unchanged; its Nginx configuration gets the new WebSocket proxy location. The backend is still a **single Uvicorn worker**, as in the earlier deployment. Camera v1 registry and evidence are memory-only and reset on a restart.

## 5. Confirm old HTTP bridge / React still works

With your Windows MJPEG bridge running as before (or restart it), verify the app at your existing private Tailscale URL. The old POST `/api/v1/sources/esp32/frame` should still return `201`, `/api/v1/sources/esp32/status` should show recent activity and React preview should change. Do not use the simulator's legacy HTTP mode at the same time as your physical bridge; that old route is a shared one-camera store.

## 6. Exercise the new WSS gateway through the deployed Nginx proxy

While on the application VM:

```bash
cd ~/comp4990-integration-starter
source .venv/bin/activate
python -m pip install 'websockets>=14,<17'
python tools/start_simulator.py --device-id cam-01 --fps 8 --duration 60
```

In a **second VM terminal while the simulator is running**:

```bash
cd ~/comp4990-integration-starter
python3 tools/check_devices.py
```

Expected `cam-01` appears, `connected` and `online` are true during delivery, `received_frames` rises quickly, `evidence_frames` rises roughly once per second, and `latest_sequence` advances. After the simulator quits, `connected` becomes false; this is expected and doesn't mean failure. The simulator defaults to `ws://127.0.0.1:8080/api/v1/ingest/ws` which is **loopback only** on the VM and traverses the new Nginx reverse proxy.

You can also check `cam-02` independently:

```bash
python tools/start_simulator.py --device-id cam-02 --fps 10 --duration 60
```

For a real cross-network private WSS test on a Mac or Windows device enrolled in your Tailscale tailnet, run the previous Phase 2 simulator with `--url wss://comp4990.tail4a8541.ts.net/api/v1/ingest/ws`, `--device-id cam-02`, and its own `SCENESENSE_CAMERA_TOKEN` set. Never send raw tokens in command arguments or screenshots. Tailscale Serve must forward WebSocket Upgrade for this to work; confirm this experimentally.

### What React will show

**The existing React camera preview continues to show only the physical-camera HTTP bridge.** WSS simulator images are available via the viewer-token-protected `/api/v1/devices/{device_id}/latest.jpg`; do not put the viewer token in React JS. A proper authenticated browser API/fanout is the next milestone. The current `POST /api/v1/analyze/esp32` analyzes the legacy store, not WSS evidence.

## 7. Rollback

If the new service fails and you have not changed the patched files again, go back to the extracted patch directory and use the backup path printed by the installer:

```bash
cd ~/COMP4990_Phase3_Integration_Patch
bash scripts/rollback.sh ~/comp4990-integration-starter ~/comp4990-backups/phase3-REPLACE-WITH-STAMP/pre-phase3-files.tar.gz
cd ~/comp4990-integration-starter
sudo docker compose up -d --build backend frontend
sudo docker compose ps
```

Rollback restores all six modified original files and removes newly copied v1 source/test/doc/simulator files. It intentionally **does not edit or print `.env`** (new camera credentials become unused). If you made changes after patch application, manually reconcile them before rollback.

## 8. Test success criteria

- Original ESP32 bridge still gets `201`; React preview works.
- New WSS simulator obtains `ready` after authenticated handshake.
- `cam-01` / `cam-02` appear separately, no identity collision.
- Viewer API requires separate viewer token; camera token cannot query images.
- Evidence stores at most 30 sampled frames, limited to 30 seconds / 6 MiB per camera.
- Invalid or expired WebSocket sessions cannot overwrite a new session.

**Not covered by this deployment:** publishing Cloudflare, flashable ESP32 direct WSS, browser WebSocket fanout, model integration of new evidence, or a tested end-to-end latency figure.
