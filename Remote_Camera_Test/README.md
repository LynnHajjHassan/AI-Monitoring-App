# SceneSense / COMP4990 — Tailscale WSS remote camera test

This is a portable **simulated camera**, not ESP32 firmware. It sends synthetic JPEG fixtures to the **already deployed** `/api/v1/ingest/ws` route over Tailscale HTTPS/WSS. It makes no modifications to the production FastAPI/React app. Use only from a computer that can access the server over Tailscale. No Cloudflare Tunnel is needed yet.

## On Windows (PowerShell)

1. Extract this ZIP, then open PowerShell in the extracted `SceneSense_Remote_Camera_Test` folder.
2. Confirm Tailscale is connected; test the known backend with:

   ```powershell
   curl.exe --fail-with-body https://comp4990.tail4a8541.ts.net/api/v1/health
   python -m pip install -r requirements.txt
   python run_remote.py --device-id cam-01 --fps 8 --duration 60
   ```

3. When prompted, paste **only cam-01's camera-v1 secret**. The prompt does not echo the token. Never enter the viewer token or the old bridge token. The token isn't written to a file or added to command-line arguments.
4. Expected: `READY device=cam-01`, followed by `WSS sent seq=...` lines. The remote WebSocket URL is `wss://comp4990.tail4a8541.ts.net/api/v1/ingest/ws`.

## On macOS

Run in Terminal in the extracted folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 run_remote.py --device-id cam-02 --fps 8 --duration 60
```

Paste **only cam-02's secret** when requested. The Mac must have access to the server's Tailscale tailnet for this private test. The teammate can instead use Phase 2's fully local demo without any credentials.

## View the server results

In an SSH session on `comp4990`, while the remote simulator is running:

```bash
cd ~/comp4990-integration-starter
python3 tools/check_devices.py
```

Expect `connected=true`, `online=true`, `received_frames` increasing, and `evidence_frames` sampled at approximately 1 per second. After the simulator stops, `connected` changes to false. The current React preview **does not show WSS camera frames yet**; it still uses the older HTTP bridge source.

## Optional reconnect test

```powershell
python run_remote.py --device-id cam-01 --fps 8 --duration 60 --drop-every 30
```

The simulator intentionally disconnects and reconnects at every 30th frame; check `connection_count` increasing on the server. Do not run another camera with the same device ID at the same time: the newer connection supersedes the older one by protocol.

## Retrieve the camera token locally on the VM

In the VM's shell (not in chat, screenshots, or shared logs), the following prints **only the cam-01 secret**. Change `cam-01` to `cam-02` for the teammate:

```bash
cd ~/comp4990-integration-starter
python3 - <<'PY'
import json
from tools._local_env import read_env
print(json.loads(read_env('.env')['CAMERA_DEVICE_TOKENS_JSON'])['cam-01'])
PY
```

This displays a sensitive credential on the terminal; copy it privately and close the terminal view afterward. Never upload `.env` or embed tokens into source control, browser JS, URLs, or command-line arguments.

## Notes

- If `curl` fails, fix Tailscale connectivity before debugging WebSockets.
- If WSS returns HTTP 404, inspect the running Nginx and FastAPI routes. A 401/403 may mean wrong device token; a TLS error requires correcting certificate validation, not bypassing it.
- This package only tests **cross-network WSS data transport**. It does not prove the real ESP32's TLS capability or camera FPS.
- `run_remote.py --url wss://another-private-host/api/v1/ingest/ws` overrides the default for a different secure endpoint.
