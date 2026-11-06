import io
import sys
from pathlib import Path
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge"))
from mjpeg_source import (MJPEGCamera, MJPEGProtocolError, _boundary_from_content_type,
                          read_mjpeg_part, stream_url)

JPEG = b"\xff\xd8test\xff\xd9"


def part(jpeg=JPEG, timestamp=123, boundary=b"frame"):
    return (b"--" + boundary + b"\r\nContent-Type: image/jpeg\r\nContent-Length: " +
            str(len(jpeg)).encode() + b"\r\nX-Capture-Uptime-Us: " +
            str(timestamp).encode() + b"\r\n\r\n" + jpeg + b"\r\n")


class FakeStream(io.BytesIO):
    def __init__(self, chunks):
        super().__init__(chunks)
        self.headers = {"Content-Type": "multipart/x-mixed-replace; boundary=frame"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class ReaderTests(unittest.TestCase):
    def test_camera_url_compatibility(self):
        self.assertEqual(stream_url("http://192.168.2.160"),
                         "http://192.168.2.160:81/api/v1/stream")
        self.assertEqual(stream_url("http://192.168.2.160:80"),
                         "http://192.168.2.160:81/api/v1/stream")
        self.assertEqual(stream_url("http://192.168.2.160:81/api/v1/stream"),
                         "http://192.168.2.160:81/api/v1/stream")
        with self.assertRaises(ValueError):
            stream_url("https://example.com")

    def test_multipart_two_frames(self):
        data = io.BytesIO(part(timestamp=1) + part(timestamp=2))
        boundary = _boundary_from_content_type('multipart/x-mixed-replace;boundary="frame"')
        self.assertEqual(read_mjpeg_part(data, boundary), (JPEG, 1))
        self.assertEqual(read_mjpeg_part(data, boundary), (JPEG, 2))
        with self.assertRaises(EOFError):
            read_mjpeg_part(data, boundary)

    def test_reject_oversized_and_bad_jpeg(self):
        oversized = b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 99999999\r\n\r\n"
        with self.assertRaises(MJPEGProtocolError):
            read_mjpeg_part(io.BytesIO(oversized), b"--frame")
        with self.assertRaises(MJPEGProtocolError):
            read_mjpeg_part(io.BytesIO(part(b"notajpeg")), b"--frame")

    def test_reject_truncated(self):
        with self.assertRaises(EOFError):
            read_mjpeg_part(io.BytesIO(part()[:-3]), b"--frame")

    def test_worker_reconnect_and_latest(self):
        calls = []
        def open_fake(*args, **kwargs):
            calls.append(True)
            return FakeStream(part(timestamp=len(calls)))
        with patch("mjpeg_source.urlopen", side_effect=open_fake):
            with MJPEGCamera("http://cam.local", retry_min_seconds=0.01,
                             retry_max_seconds=0.05, timeout_seconds=1) as cam:
                first = cam.wait_for_frame(timeout=0.5)
                self.assertIsNotNone(first)
                second = cam.wait_for_frame(after_sequence=first.sequence, timeout=0.5)
                self.assertIsNotNone(second)
                self.assertGreater(second.sequence, first.sequence)
                self.assertGreaterEqual(cam.status()["connections"], 2)

    def test_stale_frame_not_returned(self):
        cam = MJPEGCamera("http://cam.local", stale_after_seconds=0.01)
        from mjpeg_source import MJPEGFrame
        with cam._cond:
            cam._latest = MJPEGFrame(JPEG, 1, time.monotonic() - 1,
                                      "2026-11-05T00:00:00+00:00", 123)
        self.assertIsNone(cam.latest())
        self.assertIsNone(cam.wait_for_frame(timeout=0.005))


if __name__ == "__main__":
    unittest.main()
