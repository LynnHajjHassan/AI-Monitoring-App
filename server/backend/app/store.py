"""Bounded, volatile recent-frame context for one ESP32 camera."""
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from time import monotonic

MAX_AGE_SECONDS = 30.0
MAX_FRAMES = 30
MAX_BYTES = 6 * 1024 * 1024
MAX_SINGLE_FRAME = 1024 * 1024


@dataclass(frozen=True)
class Frame:
    jpeg: bytes
    received_at: str
    monotonic_received: float
    device_id: str
    capture_uptime_us: int | None


class FrameStore:
    def __init__(self) -> None:
        self._frames: deque[Frame] = deque()
        self._bytes = 0
        self._lock = Lock()

    def _expire_locked(self, now: float) -> None:
        while self._frames and (now - self._frames[0].monotonic_received > MAX_AGE_SECONDS):
            self._bytes -= len(self._frames.popleft().jpeg)
        while len(self._frames) > MAX_FRAMES or self._bytes > MAX_BYTES:
            self._bytes -= len(self._frames.popleft().jpeg)

    def add(self, jpeg: bytes, device_id: str, capture_uptime_us: int | None = None) -> Frame:
        if not (4 <= len(jpeg) <= MAX_SINGLE_FRAME) or not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
            raise ValueError("JPEG must be nonempty, validly bounded, and contain JPEG SOI/EOI markers")
        now = monotonic()
        frame = Frame(
            jpeg=jpeg,
            received_at=datetime.now(timezone.utc).isoformat(),
            monotonic_received=now,
            device_id=device_id[:100],
            capture_uptime_us=capture_uptime_us,
        )
        with self._lock:
            self._frames.append(frame)
            self._bytes += len(jpeg)
            self._expire_locked(now)
        return frame

    def snapshot(self) -> list[Frame]:
        with self._lock:
            self._expire_locked(monotonic())
            return list(self._frames)

    def clear(self) -> None:
        with self._lock:
            self._frames.clear()
            self._bytes = 0

    def stats(self) -> dict:
        frames = self.snapshot()
        latest = frames[-1] if frames else None
        age = (monotonic() - latest.monotonic_received) if latest else None
        return {
            "online": bool(latest and age is not None and age <= 5.0),
            "frame_count": len(frames),
            "buffer_bytes": sum(len(f.jpeg) for f in frames),
            "latest_received_at": latest.received_at if latest else None,
            "latest_age_seconds": round(age, 2) if age is not None else None,
            "device_id": latest.device_id if latest else None,
            "capture_uptime_us": latest.capture_uptime_us if latest else None,
        }


esp32_frames = FrameStore()
