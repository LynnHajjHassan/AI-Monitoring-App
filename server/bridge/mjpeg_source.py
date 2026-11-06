"""COMP4990: one persistent ESP32 MJPEG connection with latest-frame semantics.

Python 3.10+ standard library. Portable on Windows/macOS/Linux.
Does not know or modify the backend upload API.

Only one instance should connect to an ESP32: firmware currently allows
one long-lived MJPEG subscriber. The consumer stores a single most-recent
JPEG, rather than queueing frames that become stale while uploads run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import http.client
import logging
import threading
import time
from typing import BinaryIO, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LOG = logging.getLogger(__name__)
MAX_JPEG_BYTES = 2_000_000
MAX_LINE_BYTES = 1024


@dataclass(frozen=True)
class MJPEGFrame:
    jpeg: bytes
    sequence: int
    received_monotonic: float
    received_utc: str
    device_capture_uptime_us: Optional[int]

    @property
    def age_ms(self) -> float:
        return max(0.0, (time.monotonic() - self.received_monotonic) * 1000.0)


class MJPEGProtocolError(Exception):
    """Malformed or unacceptable multipart response."""


def stream_url(camera: str) -> str:
    """Accept the legacy camera base http://host or an explicit stream URL.

    Firmware stream server is on port 81; the existing snapshot API is on 80.
    """
    from urllib.parse import urlsplit, urlunsplit

    value = camera.rstrip("/")
    parts = urlsplit(value)
    if parts.scheme != "http" or not parts.hostname or parts.username or parts.password:
        raise ValueError("Camera must be an http:// hostname or IP on a trusted LAN")
    if parts.query or parts.fragment:
        raise ValueError("Camera URL must not contain a query or fragment")
    if parts.path not in ("", "/", "/api/v1/stream"):
        raise ValueError("Expected camera base URL or /api/v1/stream")
    # IPv6 bracket form is supported by urlsplit.hostname and urlunsplit.
    host = parts.hostname
    if ":" in host:
        host = f"[{host}]"
    port = parts.port if parts.port is not None else 81
    if port == 80 and parts.path in ("", "/"):
        port = 81  # Legacy base camera URL explicitly specifying snapshot port
    netloc = f"{host}:{port}"
    return urlunsplit(("http", netloc, "/api/v1/stream", "", ""))


def _readline(stream: BinaryIO) -> bytes:
    line = stream.readline(MAX_LINE_BYTES + 1)
    if len(line) > MAX_LINE_BYTES:
        raise MJPEGProtocolError("Multipart header line exceeds size limit")
    return line


def _read_exact(stream: BinaryIO, count: int) -> bytes:
    result = bytearray()
    while len(result) < count:
        part = stream.read(count - len(result))
        if not part:
            raise EOFError("Stream ended inside JPEG frame")
        result.extend(part)
    return bytes(result)


def _boundary_from_content_type(content_type: str) -> bytes:
    # Example: multipart/x-mixed-replace;boundary=frame
    chunks = [x.strip() for x in content_type.split(";")]
    if not chunks or chunks[0].lower() != "multipart/x-mixed-replace":
        raise MJPEGProtocolError(f"Not an MJPEG multipart response: {content_type!r}")
    for option in chunks[1:]:
        k, sep, v = option.partition("=")
        if sep and k.strip().lower() == "boundary":
            v = v.strip().strip('"')
            if not 1 <= len(v) <= 70 or any(ord(c) < 33 or ord(c) > 126 for c in v):
                raise MJPEGProtocolError("Invalid boundary value")
            if v.startswith("--"):
                v = v[2:]
            return b"--" + v.encode("ascii")
    raise MJPEGProtocolError("MJPEG response missing boundary")


def read_mjpeg_part(stream: BinaryIO, boundary: bytes) -> tuple[bytes, Optional[int]]:
    """Read one part; urllib has already decoded HTTP chunked encoding.

    The firmware provides Content-Length per part. No JPEG marker scanning is
    used for framing (JPEG payloads may contain arbitrary binary data).
    """
    for _ in range(8):
        line = _readline(stream)
        if not line:
            raise EOFError("Stream ended before next boundary")
        marker = line.strip()
        if marker == boundary:
            break
        if marker == boundary + b"--":
            raise EOFError("MJPEG stream closed")
        if marker not in (b"",):
            raise MJPEGProtocolError("Unexpected bytes before multipart boundary")
    else:
        raise MJPEGProtocolError("No multipart boundary found")

    headers: dict[str, str] = {}
    for _ in range(24):
        line = _readline(stream)
        if not line:
            raise EOFError("Stream ended in part headers")
        if line in (b"\r\n", b"\n"):
            break
        key, delim, value = line.partition(b":")
        if not delim:
            raise MJPEGProtocolError("Invalid multipart header")
        try:
            headers[key.strip().decode("ascii").lower()] = value.strip().decode("ascii")
        except UnicodeError as exc:
            raise MJPEGProtocolError("Non-ASCII multipart header") from exc
    else:
        raise MJPEGProtocolError("Too many multipart header lines")
    if headers.get("content-type", "").lower() != "image/jpeg":
        raise MJPEGProtocolError("Expected image/jpeg multipart frame")
    try:
        count = int(headers["content-length"])
    except (KeyError, ValueError) as exc:
        raise MJPEGProtocolError("Missing/invalid JPEG Content-Length") from exc
    if not (4 <= count <= MAX_JPEG_BYTES):
        raise MJPEGProtocolError(f"JPEG length out of bounds: {count}")
    jpeg = _read_exact(stream, count)
    if jpeg[:2] != b"\xff\xd8" or jpeg[-2:] != b"\xff\xd9":
        raise MJPEGProtocolError("JPEG SOI/EOI markers missing")
    raw_uptime = headers.get("x-capture-uptime-us")
    uptime = None
    if raw_uptime is not None:
        try:
            uptime = int(raw_uptime)
            if uptime < 0:
                raise ValueError("negative timestamp")
        except ValueError as exc:
            raise MJPEGProtocolError("Invalid device uptime timestamp") from exc
    return jpeg, uptime


class MJPEGCamera:
    """Background network reader. Producers never wait for an upload consumer."""

    def __init__(
        self,
        camera: str,
        *,
        timeout_seconds: float = 5.0,
        stale_after_seconds: float = 2.0,
        retry_min_seconds: float = 0.5,
        retry_max_seconds: float = 5.0,
    ) -> None:
        if timeout_seconds <= 0 or stale_after_seconds <= 0:
            raise ValueError("timeout and staleness limits must be positive")
        if retry_min_seconds <= 0 or retry_max_seconds < retry_min_seconds:
            raise ValueError("Invalid retry delay bounds")
        self.url = stream_url(camera)
        self.timeout_seconds = timeout_seconds
        self.stale_after_seconds = stale_after_seconds
        self.retry_min_seconds = retry_min_seconds
        self.retry_max_seconds = retry_max_seconds
        self._cond = threading.Condition()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._stream = None
        self._latest: Optional[MJPEGFrame] = None
        self._sequence = 0
        self._frames_received = 0
        self._connections = 0
        self._connected = False
        self._last_error: Optional[str] = None

    def start(self) -> None:
        with self._cond:
            if self._thread is not None:
                raise RuntimeError("MJPEGCamera.start() may only be called once")
            self._thread = threading.Thread(target=self._run, name="esp32-mjpeg", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._cond:
            stream = self._stream
            self._cond.notify_all()
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=self.timeout_seconds + 1.0)

    def __enter__(self) -> "MJPEGCamera":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    def _run(self) -> None:
        backoff = self.retry_min_seconds
        while not self._stop.is_set():
            try:
                request = Request(self.url, headers={"User-Agent": "COMP4990-MJPEG-Bridge/1.0"})
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    boundary = _boundary_from_content_type(response.headers.get("Content-Type", ""))
                    with self._cond:
                        self._stream = response
                        self._connected = True
                        self._connections += 1
                        self._last_error = None
                        self._cond.notify_all()
                    LOG.info("MJPEG connected: %s", self.url)
                    backoff = self.retry_min_seconds
                    while not self._stop.is_set():
                        jpeg, uptime_us = read_mjpeg_part(response, boundary)
                        now = time.monotonic()
                        with self._cond:
                            self._sequence += 1
                            self._frames_received += 1
                            self._latest = MJPEGFrame(
                                jpeg=jpeg,
                                sequence=self._sequence,
                                received_monotonic=now,
                                received_utc=datetime.now(timezone.utc).isoformat(),
                                device_capture_uptime_us=uptime_us,
                            )
                            self._cond.notify_all()
            except (HTTPError, URLError, OSError, EOFError, ValueError,
                    http.client.HTTPException, MJPEGProtocolError, AttributeError) as exc:
                # CPython's HTTPResponse.readline() can raise AttributeError if
                # stop() closes a chunked HTTP stream concurrently. Treat as
                # a transport disconnect, never as a fatal background crash.
                if not self._stop.is_set():
                    with self._cond:
                        self._last_error = f"{type(exc).__name__}: {exc}"
                    LOG.warning("MJPEG disconnected (%s); reconnecting", exc)
            finally:
                with self._cond:
                    self._stream = None
                    self._connected = False
                    self._cond.notify_all()
            if self._stop.wait(backoff):
                break
            backoff = min(backoff * 2, self.retry_max_seconds)

    def latest(self) -> Optional[MJPEGFrame]:
        with self._cond:
            frame = self._latest
        if frame is not None and frame.age_ms <= self.stale_after_seconds * 1000:
            return frame
        return None

    def wait_for_frame(self, after_sequence: int = 0, timeout: float = 3.0) -> Optional[MJPEGFrame]:
        """Wait for a *new* fresh frame; never drain old frames from a queue."""
        deadline = time.monotonic() + max(0, timeout)
        with self._cond:
            while not self._stop.is_set():
                frame = self._latest
                if (frame is not None and frame.sequence > after_sequence and
                    frame.age_ms <= self.stale_after_seconds * 1000):
                    return frame
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._cond.wait(remaining)
        return None

    def status(self) -> dict:
        with self._cond:
            frame = self._latest
            return {
                "stream_url": self.url,
                "connected": self._connected,
                "connections": self._connections,
                "frames_received": self._frames_received,
                "latest_sequence": self._sequence,
                "latest_age_ms": round(frame.age_ms) if frame is not None else None,
                "latest_fresh": frame is not None and frame.age_ms <= self.stale_after_seconds * 1000,
                "last_error": self._last_error,
            }
