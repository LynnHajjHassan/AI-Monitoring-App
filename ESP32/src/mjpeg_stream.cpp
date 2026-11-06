#include "mjpeg_stream.h"

#include <Arduino.h>
#include <WiFi.h>
#include <atomic>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "esp_camera.h"
#include "esp_http_server.h"

#ifndef MJPEG_HTTP_PORT
#define MJPEG_HTTP_PORT 81
#endif

// Must differ from the control port of the existing HTTP server (normally 32768).
#ifndef MJPEG_CTRL_PORT
#define MJPEG_CTRL_PORT 32769
#endif

namespace {
httpd_handle_t s_stream_server = nullptr;
std::atomic<bool> s_stream_in_use{false};

// HTTP multipart stream. The camera's JPEG frame buffer is returned immediately
// after the corresponding bytes have been written to the socket.
esp_err_t streamHandler(httpd_req_t *req) {
  // One long-lived stream is intentional: the laptop bridge is the only reader.
  // It should redistribute the preview to any number of frontend viewers.
  if (s_stream_in_use.exchange(true)) {
    httpd_resp_set_status(req, "503 Service Unavailable");
    httpd_resp_set_type(req, "text/plain");
    httpd_resp_sendstr(req, "MJPEG stream already has an active client");
    return ESP_OK;
  }

  esp_err_t result = httpd_resp_set_type(
      req, "multipart/x-mixed-replace;boundary=frame");
  if (result == ESP_OK) {
    httpd_resp_set_hdr(req, "Cache-Control", "no-store, no-cache, must-revalidate");
    httpd_resp_set_hdr(req, "Pragma", "no-cache");
  }

  bool first_part = true;
  while (result == ESP_OK && WiFi.status() == WL_CONNECTED) {
    camera_fb_t* fb = esp_camera_fb_get();
    if (fb == nullptr) {
      Serial.println("[MJPEG] Camera returned no frame; closing stream");
      break;
    }

    if (fb->format != PIXFORMAT_JPEG) {
      // Do not attempt an expensive conversion on the ESP32 in streaming mode.
      Serial.println("[MJPEG] Expected JPEG camera pixel format");
      esp_camera_fb_return(fb);
      break;
    }

    const uint64_t device_us =
        static_cast<uint64_t>(fb->timestamp.tv_sec) * 1000000ULL +
        static_cast<uint64_t>(fb->timestamp.tv_usec);

    // Each JPEG part supplies its own metadata. The header is NOT another
    // independent HTTP response; the bridge should parse multipart parts.
    char header[192];
    const int written = snprintf(
        header, sizeof(header),
        "Content-Type: image/jpeg\r\n"
        "Content-Length: %u\r\n"
        "X-Capture-Uptime-Us: %llu\r\n"
        "\r\n",
        static_cast<unsigned>(fb->len),
        static_cast<unsigned long long>(device_us));

    if (written < 0 || written >= static_cast<int>(sizeof(header))) {
      esp_camera_fb_return(fb);
      result = ESP_FAIL;
      break;
    }

    const char* boundary = first_part ? "--frame\r\n" : "\r\n--frame\r\n";
    first_part = false;

    result = httpd_resp_send_chunk(req, boundary, strlen(boundary));
    if (result == ESP_OK) {
      result = httpd_resp_send_chunk(req, header, static_cast<size_t>(written));
    }
    if (result == ESP_OK) {
      result = httpd_resp_send_chunk(
          req, reinterpret_cast<const char*>(fb->buf), fb->len);
    }
    esp_camera_fb_return(fb);

    // A socket failure means the bridge/browser disconnected. Return so the
    // connection can be re-established without restarting the ESP32.
    if (result != ESP_OK) {
      break;
    }
    // ESP-IDF send_chunk() uses HTTP chunked transfer encoding; the next
    // multipart part follows in a later chunk. No extra buffer is allocated.
  }

  s_stream_in_use.store(false);
  Serial.println("[MJPEG] Client disconnected / stream stopped");
  return result == ESP_OK ? ESP_OK : ESP_FAIL;
}
}  // namespace

bool startMjpegServer() {
  if (s_stream_server != nullptr) {
    return true;
  }
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.server_port = MJPEG_HTTP_PORT;
  cfg.ctrl_port = MJPEG_CTRL_PORT;
  cfg.stack_size = 8192;
  cfg.max_uri_handlers = 2;
  cfg.lru_purge_enable = false;

  const esp_err_t started = httpd_start(&s_stream_server, &cfg);
  if (started != ESP_OK) {
    Serial.printf("[MJPEG] Server start failed: 0x%x\n", started);
    s_stream_server = nullptr;
    return false;
  }

  httpd_uri_t endpoint = {};
  endpoint.uri = "/api/v1/stream";
  endpoint.method = HTTP_GET;
  endpoint.handler = streamHandler;
  endpoint.user_ctx = nullptr;

  const esp_err_t registered = httpd_register_uri_handler(s_stream_server, &endpoint);
  if (registered != ESP_OK) {
    Serial.printf("[MJPEG] Handler registration failed: 0x%x\n", registered);
    httpd_stop(s_stream_server);
    s_stream_server = nullptr;
    return false;
  }

  Serial.printf("[MJPEG] Ready: http://%s:%u/api/v1/stream\n",
                WiFi.localIP().toString().c_str(),
                static_cast<unsigned>(MJPEG_HTTP_PORT));
  return true;
}
