"""SceneSense camera WSS binary protocol v1; shared by sender, receiver and tests."""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass

MAGIC = b"SCV1"
VERSION = 1
HEADER = struct.Struct("!4sBBHIQ")  # magic, kind, flags, reserved, sequence, uptime_us
HEADER_BYTES = HEADER.size  # 20
JPEG_KIND = 1
MAX_JPEG_BYTES = 1_048_576
DEVICE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


@dataclass(frozen=True)
class CameraFrame:
    sequence: int
    uptime_us: int
    jpeg: bytes


def validate_jpeg(jpeg: bytes) -> None:
    if not (4 <= len(jpeg) <= MAX_JPEG_BYTES):
        raise ValueError("JPEG exceeds supported bounds")
    if not (jpeg.startswith(b"\xff\xd8") and jpeg.endswith(b"\xff\xd9")):
        raise ValueError("JPEG missing start/end markers")


def encode_frame(sequence: int, uptime_us: int, jpeg: bytes) -> bytes:
    validate_jpeg(jpeg)
    if not (1 <= sequence <= 0xFFFFFFFF):
        raise ValueError("sequence must be between 1 and 2^32-1")
    if not (0 <= uptime_us <= 0xFFFFFFFFFFFFFFFF):
        raise ValueError("uptime_us must be uint64")
    return HEADER.pack(MAGIC, JPEG_KIND, 0, 0, sequence, uptime_us) + jpeg


def decode_frame(payload: bytes) -> CameraFrame:
    if not (HEADER_BYTES + 4 <= len(payload) <= HEADER_BYTES + MAX_JPEG_BYTES):
        raise ValueError("invalid frame length")
    magic, kind, flags, reserved, sequence, uptime_us = HEADER.unpack_from(payload)
    if (magic, kind, flags, reserved) != (MAGIC, JPEG_KIND, 0, 0):
        raise ValueError("invalid frame header")
    if sequence == 0:
        raise ValueError("sequence 0 is reserved")
    jpeg = payload[HEADER_BYTES:]
    validate_jpeg(jpeg)
    return CameraFrame(sequence, uptime_us, jpeg)
