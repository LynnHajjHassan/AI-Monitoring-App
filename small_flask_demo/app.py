import os
from urllib.parse import urljoin   # to join the link 

import requests
from flask import Flask, Response, render_template
from flask import send_file, jsonify, request
from dotenv import load_dotenv
import time
from pathlib import Path

Path("snapshots").mkdir(exist_ok=True)

load_dotenv()  # reads .env if present 

# Set up our esp32 url
ESP32_BASE = os.getenv("ESP32_BASE_URL", "http://10.52.159.28")
STREAM_URL = f"{ESP32_BASE}:81/stream"      # default CameraWebServer stream
SNAP_URL = urljoin(ESP32_BASE + "/","capture") 

app = Flask(__name__)

@app.get("/health")
def health():
    try:
        r = requests.get(ESP32_BASE, timeout=2)
        return jsonify(ok=True, base=ESP32_BASE, status=r.status_code)
    except Exception as e:
        return jsonify(ok=False, base=ESP32_BASE, error=str(e)), 503


@app.get("/")
def index():
    # simple page that embeds our proxied stream
    return render_template("index.html")

@app.get("/video_feed")
def video_feed():
    # proxy the ESP32 MJPEG stream to the browser with the SAME Content-Type
    upstream = requests.get(STREAM_URL, stream=True, timeout=10)
    upstream.raise_for_status()

    content_type = upstream.headers.get(
        "Content-Type",
        "multipart/x-mixed-replace; boundary=frame"
    )

    def gen():
        try:
            for chunk in upstream.iter_content(chunk_size=1024):
                if not chunk:
                    break
                yield chunk
        finally:
            upstream.close()

    # IMPORTANT: use content_type, not a hard-coded mimetype
    return Response(gen(), content_type=content_type)

@app.get("/snapshot.jpg")
def snapshot():
    """
    Fetch a single JPEG from ESP32 /capture and return it to the browser.
    """
    try:
        r = requests.get(SNAP_URL, timeout=5)
        r.raise_for_status()
        return Response(r.content, mimetype="image/jpeg")
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 502


@app.get("/snapshot-save")
def snapshot_save():
    """
    Fetch a single JPEG from ESP32 /capture and save it in ./snapshots.
    """
    try:
        r = requests.get(SNAP_URL, timeout=5)
        r.raise_for_status()
        ts = time.strftime("%Y%m%d-%H%M%S")
        fname = Path("snapshots") / f"snapshot-{ts}.jpg"
        fname.write_bytes(r.content)
        return jsonify(ok=True, file=str(fname))
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 502

if __name__ == "__main__":
    print("ESP32_BASE:", ESP32_BASE)
    print("STREAM_URL:", STREAM_URL)
    app.run(host="0.0.0.0", port=5000, debug=True)


