"""Integration test: urllib decoding HTTP chunked + multipart MJPEG over local socket."""
import sys
from pathlib import Path
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge"))
from mjpeg_source import MJPEGCamera

JPEG = b"\xff\xd8bytes-over-http\xff\xd9"

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/api/v1/stream":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace;boundary=frame")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        try:
            for i in range(3):
                part = (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " +
                        str(len(JPEG)).encode() + b"\r\nX-Capture-Uptime-Us: " +
                        str(100+i).encode() + b"\r\n\r\n" + JPEG + b"\r\n")
                self.wfile.write(f"{len(part):X}\r\n".encode() + part + b"\r\n")
                self.wfile.flush()
                time.sleep(0.03)
            # Disconnection should trigger a client reconnect.
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (OSError, BrokenPipeError):
            pass

    def log_message(self, format, *args):
        pass

class HTTPIntegration(unittest.TestCase):
    def test_reader_real_local_http_chunked_and_reconnect(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        th = threading.Thread(target=server.serve_forever, daemon=True)
        th.start()
        try:
            # stream_url() preserves an explicitly specified non-80 port.
            cam = MJPEGCamera(f"http://127.0.0.1:{server.server_port}/api/v1/stream",
                              retry_min_seconds=0.02, retry_max_seconds=0.05)
            with cam:
                f1 = cam.wait_for_frame(timeout=1.0)
                self.assertIsNotNone(f1)
                self.assertEqual(f1.jpeg, JPEG)
                self.assertEqual(f1.device_capture_uptime_us, 100)
                seq = f1.sequence
                f2 = cam.wait_for_frame(after_sequence=seq, timeout=1.0)
                self.assertIsNotNone(f2)
                self.assertEqual(f2.device_capture_uptime_us, 101)
                deadline=time.monotonic()+2
                while cam.status()["connections"]<2 and time.monotonic()<deadline:
                    time.sleep(0.02)
                self.assertGreaterEqual(cam.status()["connections"],2)
        finally:
            server.shutdown()
            server.server_close()
            th.join(timeout=2)

if __name__ == "__main__":
    unittest.main()
