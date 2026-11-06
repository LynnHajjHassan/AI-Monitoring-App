# COMP4990 implementation status — November 5, 2026

## Verified by the user (prior deployed version)

- ESP32 camera firmware produces correctly oriented JPEG snapshots.
- ESP32 stand-alone page previews and keeps a bounded recent buffer.
- Windows laptop can fetch JPEG and forward frames through Tailscale HTTPS to the backend.
- Multiple consecutive frames were accepted by the deployed backend (roughly once per second).
- Dashboard loaded and worked.

## Implemented in this v0.2 release

- ESP32 camera is the **only application source**.
- Simplified FastAPI routes for source status, newest JPEG, authorized frame ingestion, and on-demand analysis.
- Bounded server RAM buffer: 30 seconds, 30 frames, and 6 MiB; the newest frame must be under 5 seconds old to count as online.
- React page for ESP32 preview, buffer statistics, question entry, and evidence-scoped results.
- One consistent analysis response schema; up to six samples selected evenly from the recent buffer.
- Camera transport script remains backward-compatible with the successfully tested protocol.
- Backend tests: 7 passed locally after source cleanup.
- Real VLM adapter remains selectable via environment variables but has not been benchmarked against the user's GPU yet.

## Not yet independently verified

- The user's updated production VM has not yet rebuilt v0.2.
- Actual browser appearance and end-to-end behavior of v0.2 after deploy.
- A working VLM model consuming real snapshots and answering correctly.
- NVIDIA passthrough/inference worker on the Proxmox GPU node.
- Remote demo hotspot behavior and away-from-home resilience.

## Next milestone

Deploy this source-cleanup update without touching the working bridge secret/Tailscale service, then switch from labeled mock mode to a real model **after** confirming how the GTX 1080 Ti will be made available to an inference worker. Evaluate answer quality and latency with controlled scenes.
