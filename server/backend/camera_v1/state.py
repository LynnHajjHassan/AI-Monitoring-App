"""Per-device latest preview and independently sampled, bounded evidence."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from time import monotonic
from uuid import uuid4

from .protocol import CameraFrame

EVIDENCE_SECONDS = 30.0
EVIDENCE_INTERVAL_SECONDS = 1.0
MAX_EVIDENCE_FRAMES = 30
MAX_EVIDENCE_BYTES = 6 * 1024 * 1024
FRAME_FRESH_SECONDS = 5.0


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class EvidenceFrame:
    jpeg: bytes
    received_monotonic: float
    received_at: str
    sequence: int
    uptime_us: int


@dataclass
class DeviceState:
    device_id: str
    session_id: str | None = None
    socket: object | None = None
    connected: bool = False
    latest: EvidenceFrame | None = None
    evidence: deque[EvidenceFrame] = field(default_factory=deque)
    evidence_bytes: int = 0
    last_sample_time: float | None = None
    last_sequence: int = 0
    last_uptime_us: int = 0
    received_count: int = 0
    dropped_count: int = 0
    connection_count: int = 0
    last_error: str | None = None


class CameraRegistry:
    def __init__(self):
        self._lock = RLock()
        self._devices: dict[str, DeviceState] = {}

    def reset(self):  # Test fixture only; not called by production routes.
        with self._lock:
            self._devices.clear()

    def connect(self, device_id: str, socket: object) -> tuple[str, object | None]:
        with self._lock:
            state = self._devices.setdefault(device_id, DeviceState(device_id))
            prior = state.socket
            state.socket = socket
            state.session_id = str(uuid4())
            state.connected = True
            state.connection_count += 1
            state.last_sequence = 0
            state.last_uptime_us = 0
            state.last_sample_time = None  # Always sample first frame in new session
            state.latest = None  # Never show previous-session frame as current
            state.last_error = None
            return state.session_id, prior

    def disconnect(self, device_id: str, session_id: str, reason: str | None = None):
        with self._lock:
            state = self._devices.get(device_id)
            if state is not None and state.session_id == session_id:
                state.connected = False
                state.socket = None
                if reason:
                    state.last_error = reason[:160]

    def _expire(self, state: DeviceState, now: float):
        while state.evidence and now - state.evidence[0].received_monotonic > EVIDENCE_SECONDS:
            state.evidence_bytes -= len(state.evidence.popleft().jpeg)
        while len(state.evidence) > MAX_EVIDENCE_FRAMES or state.evidence_bytes > MAX_EVIDENCE_BYTES:
            state.evidence_bytes -= len(state.evidence.popleft().jpeg)

    def receive(self, device_id: str, session_id: str, frame: CameraFrame) -> bool:
        """Accept strictly increasing sequence/uptime. Returns True if AI evidence sampled."""
        now = monotonic()
        with self._lock:
            state = self._devices[device_id]
            if state.session_id != session_id or not state.connected:
                raise ValueError("superseded camera session")
            if frame.sequence <= state.last_sequence:
                state.dropped_count += 1
                raise ValueError("non-increasing frame sequence")
            if frame.uptime_us < state.last_uptime_us:
                state.dropped_count += 1
                raise ValueError("non-increasing capture uptime")
            received = EvidenceFrame(frame.jpeg, now, iso_now(), frame.sequence, frame.uptime_us)
            state.latest = received
            state.last_sequence = frame.sequence
            state.last_uptime_us = frame.uptime_us
            state.received_count += 1
            self._expire(state, now)
            if state.last_sample_time is None or (now - state.last_sample_time) >= EVIDENCE_INTERVAL_SECONDS:
                state.evidence.append(received)
                state.evidence_bytes += len(received.jpeg)
                state.last_sample_time = now
                self._expire(state, now)
                return True
            return False

    def status(self, device_id: str) -> dict | None:
        now = monotonic()
        with self._lock:
            state = self._devices.get(device_id)
            if state is None:
                return None
            self._expire(state, now)
            age = round(now - state.latest.received_monotonic, 3) if state.latest else None
            online = bool(state.connected and age is not None and age <= FRAME_FRESH_SECONDS)
            return {
                "device_id": state.device_id,
                "connected": state.connected,
                "online": online,
                "stale": bool(state.connected and not online),
                "session_id": state.session_id,
                "latest_received_at": state.latest.received_at if state.latest else None,
                "latest_age_seconds": age,
                "latest_sequence": state.latest.sequence if state.latest else None,
                "received_frames": state.received_count,
                "dropped_frames": state.dropped_count,
                "evidence_frames": len(state.evidence),
                "evidence_bytes": state.evidence_bytes,
                "connection_count": state.connection_count,
                "last_error": state.last_error,
            }

    def statuses(self) -> list[dict]:
        with self._lock:
            ids = sorted(self._devices)
        return [result for device_id in ids if (result := self.status(device_id)) is not None]

    def latest(self, device_id: str) -> bytes | None:
        with self._lock:
            state = self._devices.get(device_id)
            if state is None or not state.connected or state.latest is None:
                return None
            if monotonic() - state.latest.received_monotonic > FRAME_FRESH_SECONDS:
                return None
            return state.latest.jpeg

    def evidence(self, device_id: str) -> list[EvidenceFrame]:
        with self._lock:
            state = self._devices.get(device_id)
            if state is None:
                return []
            self._expire(state, monotonic())
            return list(state.evidence)


registry = CameraRegistry()
