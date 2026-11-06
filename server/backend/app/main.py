"""COMP4990 ESP32-only API: live evidence upload, preview, and on-demand VLM Q&A."""
import hmac
import os
from time import monotonic

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .inference import answer_question, select_evenly
from .store import MAX_SINGLE_FRAME, esp32_frames
from camera_v1.routes import router as camera_v1_router

app = FastAPI(
    title="COMP4990 ESP32 Video Understanding", version="0.2.0",
    docs_url="/api/docs", openapi_url="/api/openapi.json",
)
app.include_router(camera_v1_router)


class Prompt(BaseModel):
    question: str = Field(min_length=2, max_length=500)


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok", "inference_mode": os.environ.get("INFERENCE_MODE", "mock")}


@app.get("/api/v1/sources/esp32/status")
def source_status() -> dict:
    return esp32_frames.stats()


@app.get("/api/v1/sources/esp32/latest.jpg")
def latest_esp32_frame() -> Response:
    frames = esp32_frames.snapshot()
    status = esp32_frames.stats()
    if not frames or not status["online"]:
        raise HTTPException(404, "No recent ESP32 frame (bridge may be offline)")
    return Response(
        content=frames[-1].jpeg,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/v1/sources/esp32/frame", status_code=201)
async def ingest_esp32(
    request: Request,
    authorization: str | None = Header(default=None),
    x_device_id: str | None = Header(default=None),
    x_capture_uptime_us: str | None = Header(default=None),
) -> dict:
    expected = os.environ.get("BRIDGE_TOKEN", "")
    if not expected or expected == "REPLACE_WITH_A_LONG_RANDOM_TOKEN":
        raise HTTPException(503, "Bridge token not configured on backend")
    supplied = (authorization or "").removeprefix("Bearer ")
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, "Invalid bridge token")
    if request.headers.get("content-type", "").split(";")[0].strip() != "image/jpeg":
        raise HTTPException(415, "Expected image/jpeg request body")

    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_SINGLE_FRAME:
            raise HTTPException(413, "Camera frame too large")
    uptime = None
    if x_capture_uptime_us is not None:
        try:
            uptime = int(x_capture_uptime_us)
            if uptime < 0:
                raise ValueError("negative uptime")
        except ValueError as exc:
            raise HTTPException(422, "Invalid X-Capture-Uptime-Us") from exc
    try:
        frame = esp32_frames.add(
            bytes(data), device_id=x_device_id or "esp32-s3", capture_uptime_us=uptime,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"accepted": True, "received_at": frame.received_at, "buffer": esp32_frames.stats()}


@app.post("/api/v1/analyze/esp32")
async def analyze_esp32(payload: Prompt) -> dict:
    start = monotonic()
    frames = esp32_frames.snapshot()
    if not frames or not esp32_frames.stats()["online"]:
        raise HTTPException(409, "ESP32 has no fresh frames; start the laptop bridge")
    chosen = select_evenly(frames)
    stamps = [frame.received_at for frame in chosen]
    answer, mode = await answer_question(payload.question, [frame.jpeg for frame in chosen], stamps)
    return {
        "source_type": "esp32",
        "source_id": chosen[-1].device_id,
        "question": payload.question,
        "answer": answer,
        "inference_mode": mode,
        "time_window": {"start": stamps[0], "end": stamps[-1]},
        "evidence": {
            "type": "sampled_jpeg_frames", "frame_count": len(chosen),
            "buffer_frame_count": len(frames),
        },
        "uncertainty": (
            "Frames were sampled rather than recorded as continuous video. "
            "Brief events between frames may have been missed."
        ),
        "processing_ms": round((monotonic() - start) * 1000),
    }
