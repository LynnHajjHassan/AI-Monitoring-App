import os
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import app, esp32_frames
from app.store import FrameStore, MAX_BYTES, MAX_FRAMES

client = TestClient(app)
JPEG = b"\xff\xd8\xff\xe0COMP4990TEST\xff\xd9"  # API boundary fixture, not a decoded image.


def setup_function():
    esp32_frames.clear()


def test_health_is_explicitly_mock():
    with patch.dict(os.environ, {"INFERENCE_MODE": "mock"}):
        result = client.get("/api/v1/health")
    assert result.status_code == 200
    assert result.json()["inference_mode"] == "mock"


def test_ingestion_requires_bridge_secret():
    with patch.dict(os.environ, {"BRIDGE_TOKEN": "test-only-secret"}):
        unauth = client.post("/api/v1/sources/esp32/frame", content=JPEG, headers={"content-type": "image/jpeg"})
        assert unauth.status_code == 401
        auth = client.post(
            "/api/v1/sources/esp32/frame", content=JPEG,
            headers={"content-type": "image/jpeg", "authorization": "Bearer test-only-secret", "X-Device-Id": "testcam", "X-Capture-Uptime-Us": "42"},
        )
    assert auth.status_code == 201
    assert client.get("/api/v1/sources/esp32/status").json()["device_id"] == "testcam"
    assert client.get("/api/v1/sources/esp32/latest.jpg").content == JPEG


def test_esp32_analysis_labels_mock_and_window():
    esp32_frames.add(JPEG, "cam")
    with patch.dict(os.environ, {"INFERENCE_MODE": "mock"}):
        result = client.post("/api/v1/analyze/esp32", json={"question": "What do you see?"})
    assert result.status_code == 200
    payload = result.json()
    assert payload["inference_mode"] == "mock"
    assert "No image understanding has run" in payload["answer"]
    assert payload["evidence"]["frame_count"] == 1
    assert payload["source_type"] == "esp32"
    assert payload["time_window"]["start"]


def test_rolling_frame_caps_and_inference_sampling():
    store = FrameStore()
    for _ in range(60):
        store.add(JPEG, "cap")
    assert len(store.snapshot()) <= MAX_FRAMES
    assert store.stats()["buffer_bytes"] <= MAX_BYTES

    for _ in range(17):
        esp32_frames.add(JPEG, "cap")
    with patch.dict(os.environ, {"INFERENCE_MODE": "mock"}):
        response = client.post("/api/v1/analyze/esp32", json={"question": "Any changes?"})
    assert response.status_code == 200
    evidence = response.json()["evidence"]
    assert evidence["frame_count"] == 6
    assert evidence["buffer_frame_count"] == 17


def test_esp32_empty_error_and_missing_token():
    with patch.dict(os.environ, {"BRIDGE_TOKEN": ""}):
        assert client.post("/api/v1/sources/esp32/frame", content=JPEG, headers={"content-type": "image/jpeg"}).status_code == 503
    assert client.post("/api/v1/analyze/esp32", json={"question": "What happened?"}).status_code == 409


def test_invalid_jpeg_and_bad_capture_uptime():
    with patch.dict(os.environ, {"BRIDGE_TOKEN": "test-only-secret"}):
        headers = {"Content-Type": "image/jpeg", "Authorization": "Bearer test-only-secret"}
        assert client.post("/api/v1/sources/esp32/frame", content=b"notjpeg", headers=headers).status_code == 422
        assert client.post("/api/v1/sources/esp32/frame", content=JPEG, headers={**headers, "X-Capture-Uptime-Us": "bad"}).status_code == 422


def test_removed_sources_are_not_registered():
    paths = set(app.openapi()["paths"]) | {route.path for route in app.routes if hasattr(route, "path")}
    assert {
        "/api/docs", "/api/openapi.json", "/docs/oauth2-redirect", "/redoc", "/api/v1/health",
        "/api/v1/sources/esp32/status", "/api/v1/sources/esp32/latest.jpg",
        "/api/v1/sources/esp32/frame", "/api/v1/analyze/esp32",
    } <= paths
    assert not any("webcam" in path or "upload" in path for path in paths)
