# Cloudflare Tunnel — follow-on gateway design (not deployed)

Use only after the private WSS test succeeds through Nginx/Tailscale. The domain must be on Cloudflare before public hostname routing can be configured. Do not modify the Hostinger domain's nameserver or production website unexpectedly.

Cloudflare Tunnel can accept inbound client WebSocket traffic through an **outbound** `cloudflared` connector on the application VM. A camera could use:

```text
wss://camera.YOUR_DOMAIN.example/api/v1/ingest/ws
```

## Restrict public traffic to exactly camera ingress

A *locally managed* `cloudflared` tunnel can use path regular expressions with a deny-all fallback. The following is a **design example only**; replace credentials/tunnel ID and hostname with real values when ready:

```yaml
# NOT a live tunnel configuration. Do not copy credentials into Git.
tunnel: YOUR_TUNNEL_UUID
credentials-file: /PATH/TO/PRIVATE/CREDENTIALS.json
ingress:
  - hostname: camera.YOUR_DOMAIN.example
    path: ^/api/v1/ingest/ws$
    service: http://127.0.0.1:8080
  - hostname: camera.YOUR_DOMAIN.example
    service: http_status:404
  - service: http_status:404
```

This configuration intends to publish the camera WebSocket upgrade endpoint **only**, not `/api/v1/devices/*`, `/api/v1/sources/esp32/*`, `/api/v1/analyze/esp32`, or the React frontend. Test path normalization, unexpected URL encodings and fallthrough routes before production. The `http_status:404` fallback is not authentication; FastAPI must still validate per-device bearer tokens.

Current official documentation: https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/configuration-file/ ; https://developers.cloudflare.com/tunnel/concepts/ . Cloudflare Tunnel requires service setup and TLS configuration that is **not** included in this code patch.

**Do not put bearer tokens in URLs**. The ESP32 must verify Cloudflare's public TLS certificate and have a valid clock for certificate validation. Camera credentials are separate per device. Limit image message sizes at the origin and monitor network/CPU usage. Avoid publishing the entire existing application, since the original one-camera routes do not currently enforce a user login.

Once public ingress is verified from an external hotspot, implement firmware's direct WSS state machine (`WIFI_DOWN`, `WIFI_CONNECTING`, `TLS_CONNECTING`, `AUTHENTICATING`, `STREAMING`, `BACKOFF`). Keep local `/health`, `/api/v1/capture` and MJPEG diagnostics for rollback.
