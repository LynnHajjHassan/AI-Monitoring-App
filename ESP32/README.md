# COMP4990 Streaming Phase 2 — laptop MJPEG reader

Phase 1 firmware is verified working at 4.78 FPS by the user. This package provides a portable standalone MJPEG consumer to *add* to the current authenticated bridge. It does not change ESP32 firmware or the existing FastAPI API contract. See `docs/PHASE2_INTEGRATION.md` before patching.

Contents: `bridge/mjpeg_source.py`, `tools/check_bridge_stream.py`, `tests/test_mjpeg_source.py`.

Quick validation from this package folder:

```bash
python -m unittest discover -s tests -v
python tools/check_bridge_stream.py --camera http://192.168.2.160 --seconds 30
```

Stop other MJPEG clients first. Firmware accepts one at a time.
