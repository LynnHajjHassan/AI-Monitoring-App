"""Additive, opt-in camera WebSocket API; doesn't modify legacy routes."""
from __future__ import annotations

import asyncio
import hmac
import json
import os
from json import JSONDecodeError

from fastapi import APIRouter, Depends, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from .protocol import DEVICE_RE, MAX_JPEG_BYTES, decode_frame
from .state import registry

router = APIRouter()
HELLO_TIMEOUT_SECONDS = 5.0
IDLE_TIMEOUT_SECONDS = 35.0
MAX_TEXT_BYTES = 2048


def get_camera_tokens() -> dict[str, str]:
    raw = os.environ.get("CAMERA_DEVICE_TOKENS_JSON", "")
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
    except JSONDecodeError as exc:
        raise RuntimeError("CAMERA_DEVICE_TOKENS_JSON is invalid JSON") from exc
    if not isinstance(obj, dict) or not (1 <= len(obj) <= 16):
        raise RuntimeError("CAMERA_DEVICE_TOKENS_JSON must map 1-16 camera IDs to tokens")
    if any(not isinstance(k, str) or not DEVICE_RE.fullmatch(k) or not isinstance(v, str) or len(v) < 24 for k, v in obj.items()):
        raise RuntimeError("Camera IDs must be valid and tokens at least 24 characters")
    if len(set(obj.values())) != len(obj):
        raise RuntimeError("Every camera requires its own unique token")
    return obj


def authorized(authorization: str | None, token: str) -> bool:
    if not authorization or not authorization.startswith("Bearer ") or not token:
        return False
    return hmac.compare_digest(authorization[7:], token)


def viewer_auth(authorization: str | None = Header(default=None)) -> None:
    viewer_token = os.environ.get("CAMERA_VIEWER_TOKEN", "")
    if len(viewer_token) < 24:
        raise HTTPException(503, "Viewer token not configured")
    if not authorized(authorization, viewer_token):
        raise HTTPException(401, "Invalid viewer token")


@router.get("/api/v1/devices", dependencies=[Depends(viewer_auth)])
def list_devices() -> dict:
    return {"devices": registry.statuses()}


@router.get("/api/v1/devices/{device_id}/status", dependencies=[Depends(viewer_auth)])
def get_device_status(device_id: str) -> dict:
    status = registry.status(device_id)
    if status is None:
        raise HTTPException(404, "Unknown device")
    return status


@router.get("/api/v1/devices/{device_id}/latest.jpg", dependencies=[Depends(viewer_auth)])
def get_latest(device_id: str) -> Response:
    latest = registry.latest(device_id)
    if latest is None:
        raise HTTPException(404, "No recent connected camera frame")
    return Response(latest, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/api/v1/devices/{device_id}/evidence", dependencies=[Depends(viewer_auth)])
def get_evidence_summary(device_id: str) -> dict:
    status = registry.status(device_id)
    if status is None:
        raise HTTPException(404, "Unknown device")
    return {
        "device_id": device_id,
        "frames": [
            {"sequence": frame.sequence, "received_at": frame.received_at, "uptime_us": frame.uptime_us}
            for frame in registry.evidence(device_id)
        ],
        "sampling_interval_seconds": 1,
        "window_seconds": 30,
    }


async def receive_json(ws: WebSocket, timeout: float) -> dict:
    text = await asyncio.wait_for(ws.receive_text(), timeout=timeout)
    if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        raise ValueError("message too long")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("expected JSON object")
    return data


@router.websocket("/api/v1/ingest/ws")
async def ingest_ws(ws: WebSocket) -> None:
    device_id = ws.headers.get("x-device-id", "")
    try:
        tokens = get_camera_tokens()
    except RuntimeError:
        # Configuration error: do not leak secrets or configuration in response.
        await ws.close(code=1011)
        return
    if not DEVICE_RE.fullmatch(device_id) or device_id not in tokens or not authorized(ws.headers.get("authorization"), tokens[device_id]):
        await ws.close(code=1008)
        return
    await ws.accept()
    try:
        hello = await receive_json(ws, HELLO_TIMEOUT_SECONDS)
        if (set(hello) != {"type", "version", "device_id"}
                or hello != {"type": "hello", "version": 1, "device_id": device_id}):
            await ws.close(code=1008, reason="invalid hello")
            return
    except (ValueError, JSONDecodeError, WebSocketDisconnect, asyncio.TimeoutError, RuntimeError):
        await ws.close(code=1008, reason="hello required")
        return

    session_id, old_ws = registry.connect(device_id, ws)
    if old_ws is not None and old_ws is not ws:
        try:
            await old_ws.close(code=4001, reason="superseded")
        except (RuntimeError, OSError):
            pass
    await ws.send_json({
        "type": "ready", "version": 1, "device_id": device_id,
        "session_id": session_id,
        "limits": {"max_jpeg_bytes": MAX_JPEG_BYTES, "heartbeat_interval_seconds": 15},
    })
    reason = None
    try:
        while True:
            message = await asyncio.wait_for(ws.receive(), timeout=IDLE_TIMEOUT_SECONDS)
            if message["type"] == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                try:
                    frame = decode_frame(message["bytes"])
                    registry.receive(device_id, session_id, frame)
                except ValueError:
                    reason = "invalid frame or sequence"
                    await ws.close(code=1008, reason=reason)
                    break
            elif message.get("text") is not None:
                try:
                    text = message["text"]
                    if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
                        raise ValueError("message too long")
                    data = json.loads(text)
                    if data != {"type": "heartbeat"}:
                        raise ValueError("invalid message")
                except (ValueError, JSONDecodeError):
                    reason = "invalid control message"
                    await ws.close(code=1008, reason=reason)
                    break
                await ws.send_json({"type": "heartbeat_ack"})
    except asyncio.TimeoutError:
        reason = "idle timeout"
        await ws.close(code=1001, reason=reason)
    except WebSocketDisconnect:
        pass
    finally:
        registry.disconnect(device_id, session_id, reason)
