# Mac teammate — camera v1 simulation after FastAPI integration

You do **not** need to move the Proxmox servers or plug an ESP32 into the Mac.

## Option A: Independent local development (no Tailscale)

Use the earlier Phase 2 standalone ZIP. On macOS, inside that extracted package:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python tools/demo_local.py
```

This runs two simulated cameras and validates the v1 API contract on the Mac. Use it to implement UI mocks and test API schema assumptions. No production credentials needed.

## Option B: Send a simulated camera to the shared `comp4990` app VM

Only after Phase 3 has been applied to the VM and **if the Mac has Tailscale access to the same tailnet**:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install 'websockets>=14,<17'
printf 'Enter cam-02 token (hidden): '
read -rs SCENESENSE_CAMERA_TOKEN
printf '\n'
export SCENESENSE_CAMERA_TOKEN
python simulator/sim_camera.py \
  --mode ws \
  --url wss://comp4990.tail4a8541.ts.net/api/v1/ingest/ws \
  --device-id cam-02 \
  --fps 8 --duration 30
unset SCENESENSE_CAMERA_TOKEN
```

The developer should provide **only** cam-02's token through a secure exchange, never the complete `.env` or viewer token. Avoid storing tokens in shell history; enter them interactively, or supply them via a local credential manager. Test on the Mac and only share logs with credentials redacted.

**Current React limitation:** the web UI still uses the legacy one-camera source. New simulated-camera frames are in the v1 registry, not shown in the legacy preview/analysis until a later frontend/backend bridge is developed. This is intentional for compatibility.
