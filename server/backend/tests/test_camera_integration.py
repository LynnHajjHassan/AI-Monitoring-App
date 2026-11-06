"""Integration regressions for SceneSense camera v1 alongside the working ESP32 API."""
import json
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app, esp32_frames
from camera_v1.protocol import encode_frame
from camera_v1.state import registry

LEGACY_JPEG = b"\xff\xd8legacy-frame\xff\xd9"
WS_JPEG_A = b"\xff\xd8camera-01\xff\xd9"
WS_JPEG_B = b"\xff\xd8camera-02\xff\xd9"

TOKEN_A = "cam01_integration_test_secret_abcdefgh"
TOKEN_B = "cam02_integration_test_secret_abcdefgh"
VIEWER = "viewer_integration_test_secret_abcdefgh"
ENV = {
    "BRIDGE_TOKEN": "legacy_integration_secret",
    "CAMERA_DEVICE_TOKENS_JSON": json.dumps({"cam-01": TOKEN_A, "cam-02": TOKEN_B}),
    "CAMERA_VIEWER_TOKEN": VIEWER,
    "INFERENCE_MODE": "mock",
}


@pytest.fixture(autouse=True)
def clean_state():
    registry.reset()
    esp32_frames.clear()
    yield
    registry.reset()
    esp32_frames.clear()


@pytest.fixture
def client():
    with patch.dict(os.environ, ENV):
        with TestClient(app) as http:
            yield http


def viewer_headers():
    return {"Authorization": f"Bearer {VIEWER}"}


def connect(client, name, token):
    return client.websocket_connect("/api/v1/ingest/ws", headers={"Authorization": f"Bearer {token}", "X-Device-Id": name})


def ready(ws, device):
    ws.send_json({"type": "hello", "version": 1, "device_id": device})
    assert ws.receive_json()["type"] == "ready"


def flush(ws):
    ws.send_json({"type": "heartbeat"})
    assert ws.receive_json() == {"type": "heartbeat_ack"}


def test_legacy_http_ingestion_and_react_preview_unmodified(client):
    response = client.post("/api/v1/sources/esp32/frame", content=LEGACY_JPEG, headers={
        "Content-Type": "image/jpeg", "Authorization": "Bearer legacy_integration_secret",
        "X-Device-Id": "esp32-s3", "X-Capture-Uptime-Us": "1000000",
    })
    assert response.status_code == 201
    assert client.get("/api/v1/sources/esp32/latest.jpg").content == LEGACY_JPEG
    assert client.get("/api/v1/sources/esp32/status").json()["online"] is True
    with patch.dict(os.environ, {"INFERENCE_MODE": "mock"}):
        analysis = client.post("/api/v1/analyze/esp32", json={"question": "What changed?"})
    assert analysis.status_code == 200
    assert analysis.json()["inference_mode"] == "mock"


def test_two_new_devices_separate_from_each_other_and_legacy(client):
    with connect(client, "cam-01", TOKEN_A) as a:
        ready(a, "cam-01")
        with connect(client, "cam-02", TOKEN_B) as b:
            ready(b, "cam-02")
            a.send_bytes(encode_frame(1, 123, WS_JPEG_A))
            b.send_bytes(encode_frame(1, 456, WS_JPEG_B))
            flush(a)
            flush(b)
            assert client.get("/api/v1/devices/cam-01/latest.jpg", headers=viewer_headers()).content == WS_JPEG_A
            assert client.get("/api/v1/devices/cam-02/latest.jpg", headers=viewer_headers()).content == WS_JPEG_B
            status = client.get("/api/v1/devices", headers=viewer_headers()).json()["devices"]
            assert {row["device_id"] for row in status} == {"cam-01", "cam-02"}
            assert all(row["received_frames"] == 1 and row["evidence_frames"] == 1 for row in status)
            assert client.get("/api/v1/sources/esp32/status").json()["frame_count"] == 0


def test_authentication_boundaries(client):
    assert client.get("/api/v1/devices").status_code == 401
    assert client.get("/api/v1/devices", headers={"Authorization": f"Bearer {TOKEN_A}"}).status_code == 401
    assert client.get("/api/v1/devices", headers=viewer_headers()).status_code == 200
    with pytest.raises(Exception):
        with connect(client, "cam-01", TOKEN_B):
            pass
    with connect(client, "cam-01", TOKEN_A) as ws:
        ws.send_json({"type": "hello", "version": 1, "device_id": "cam-02"})
        with pytest.raises(Exception):
            ws.receive_json()


def test_malformed_frame_does_not_update_latest(client):
    with connect(client, "cam-01", TOKEN_A) as ws:
        ready(ws, "cam-01")
        bad = bytearray(encode_frame(1, 100, WS_JPEG_A))
        bad[0] = 0x00
        ws.send_bytes(bad)
        with pytest.raises(Exception):
            ws.receive_json()
    assert client.get("/api/v1/devices/cam-01/latest.jpg", headers=viewer_headers()).status_code == 404


def test_without_camera_tokens_old_http_ingest_still_works():
    with patch.dict(os.environ, {"BRIDGE_TOKEN": "legacy_integration_secret", "CAMERA_DEVICE_TOKENS_JSON": "", "CAMERA_VIEWER_TOKEN": ""}):
        with TestClient(app) as client:
            response = client.post("/api/v1/sources/esp32/frame", content=LEGACY_JPEG, headers={
                "Content-Type": "image/jpeg", "Authorization": "Bearer legacy_integration_secret"
            })
            assert response.status_code == 201
            assert client.get("/api/v1/devices").status_code == 503
            with pytest.raises(Exception):
                with connect(client, "cam-01", TOKEN_A):
                    pass
