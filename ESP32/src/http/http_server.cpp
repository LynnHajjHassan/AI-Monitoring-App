#include <Arduino.h>
#include <esp_http_server.h>

#include "config.h"
#include "http_server.h"
#include "preview_page.h"
#include "camera/camera_service.h"
#include "network/wifi_service.h"



namespace
{
    httpd_handle_t server = nullptr;
    bool serverReady = false;

    esp_err_t previewHandler(httpd_req_t* req)
    {
        httpd_resp_set_type(req, "text/html; charset=utf-8");
        httpd_resp_set_hdr(req, "Cache-Control", "no-store");
        return httpd_resp_send(req, PREVIEW_PAGE, HTTPD_RESP_USE_STRLEN);
    }


    // ========================================
    // GET /health
    // ========================================

    esp_err_t healthHandler(httpd_req_t* req)
    {
        String response =
            "{\"status\":\"ok\",\"device\":\"" +
            String(DEVICE_ID) +
            "\"}";

        httpd_resp_set_type(
            req,
            "application/json"
        );

        httpd_resp_set_hdr(
            req,
            "Cache-Control",
            "no-store"
        );

        return httpd_resp_send(
            req,
            response.c_str(),
            response.length()
        );
    }

    // ========================================
    // GET /api/v1/status
    // ========================================

    esp_err_t statusHandler(httpd_req_t* req)
    {
        char response[512];

        String ipAddress = WiFiService::ip().toString();

        int length = snprintf(
            response,
            sizeof(response),

            "{"
                "\"device_id\":\"%s\","
                "\"firmware\":\"%s\","
                "\"status\":\"%s\","
                "\"camera\":%s,"
                "\"sensor\":\"OV5640\","
                "\"resolution\":\"%s\","
                "\"vflip\":%s,"
                "\"hmirror\":%s,"
                "\"ip\":\"%s\","
                "\"rssi\":%d,"
                "\"free_heap\":%u,"
                "\"free_psram\":%u,"
                "\"uptime_ms\":%lu"
            "}",

            DEVICE_ID,
            DEVICE_VERSION,

            CameraService::ready() ? "ready" : "error",

            CameraService::ready() ? "true" : "false",

            CAMERA_RESOLUTION_NAME,
            CAMERA_VFLIP ? "true" : "false",
            CAMERA_HMIRROR ? "true" : "false",

            ipAddress.c_str(),

            WiFiService::rssi(),

            ESP.getFreeHeap(),
            ESP.getFreePsram(),

            millis()
        );


        if (length < 0 || length >= sizeof(response))
        {
            httpd_resp_set_status(
                req,
                "500 Internal Server Error"
            );

            return httpd_resp_send(
                req,
                nullptr,
                0
            );
        }


        httpd_resp_set_type(
            req,
            "application/json"
        );

        httpd_resp_set_hdr(
            req,
            "Cache-Control",
            "no-store"
        );

        return httpd_resp_send(
            req,
            response,
            length
        );
    }

    // ========================================
    // GET /api/v1/capture
    // ========================================

    esp_err_t captureHandler(httpd_req_t* req)
    {
        if (!CameraService::ready())
        {
            httpd_resp_set_status(
                req,
                "503 Service Unavailable"
            );

            httpd_resp_set_type(
                req,
                "application/json"
            );

            const char* response =
                "{\"error\":\"camera unavailable\"}";

            return httpd_resp_send(
                req,
                response,
                HTTPD_RESP_USE_STRLEN
            );
        }


        // Acquire a framebuffer from the camera
        camera_fb_t* frame = CameraService::capture();

        if (frame == nullptr)
        {
            httpd_resp_set_status(
                req,
                "500 Internal Server Error"
            );

            httpd_resp_set_type(
                req,
                "application/json"
            );

            const char* response =
                "{\"error\":\"capture failed\"}";

            return httpd_resp_send(
                req,
                response,
                HTTPD_RESP_USE_STRLEN
            );
        }

        Serial.printf(
            "[HTTP] Capture: %u bytes (%ux%u)\n",
            frame->len,
            frame->width,
            frame->height
        );


        // Configure response as JPEG
        httpd_resp_set_type(
            req,
            "image/jpeg"
        );

        httpd_resp_set_hdr(
            req,
            "Cache-Control",
            "no-store"
        );


        // Monotonic sensor capture time, not UTC or HTTP response time.
        char capturedAt[24];
        snprintf(capturedAt, sizeof(capturedAt), "%llu",
                 static_cast<unsigned long long>(frame->timestamp.tv_sec) * 1000000ULL +
                 frame->timestamp.tv_usec);
        httpd_resp_set_hdr(req, "X-Capture-Uptime-Us", capturedAt);
        httpd_resp_set_hdr(req, "X-Device-Id", DEVICE_ID);

        // Send JPEG directly from framebuffer
        esp_err_t result = httpd_resp_send(
            req,
            reinterpret_cast<const char*>(frame->buf),
            frame->len
        );


        // Always return framebuffer to camera driver
        CameraService::release(frame);

        return result;
    }
  
  }


namespace HttpServer
{

bool begin()
{
    if (serverReady)
    {
        return true;
    }

    Serial.println("[HTTP] Starting server...");

    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = HTTP_PORT;

    esp_err_t err = httpd_start(&server, &config);

    if (err != ESP_OK)
    {
        Serial.printf(
            "[HTTP] ERROR: Failed to start server: 0x%X\n",
            err
        );

        server = nullptr;
        serverReady = false;
        return false;
    }


    // ========================================
    // Register /health
    // ========================================

    httpd_uri_t healthUri = {};

    healthUri.uri      = "/health";
    healthUri.method   = HTTP_GET;
    healthUri.handler  = healthHandler;
    healthUri.user_ctx = nullptr;

    err = httpd_register_uri_handler(
        server,
        &healthUri
    );

    if (err != ESP_OK)
    {
        Serial.printf(
            "[HTTP] ERROR: Failed to register /health: 0x%X\n",
            err
        );

        httpd_stop(server);
        server = nullptr;
        serverReady = false;

        return false;
    }


    // ========================================
    // Register /api/v1/status
    // ========================================

    httpd_uri_t statusUri = {};

    statusUri.uri      = "/api/v1/status";
    statusUri.method   = HTTP_GET;
    statusUri.handler  = statusHandler;
    statusUri.user_ctx = nullptr;

    err = httpd_register_uri_handler(
        server,
        &statusUri
    );

    if (err != ESP_OK)
    {
        Serial.printf(
            "[HTTP] ERROR: Failed to register /api/v1/status: 0x%X\n",
            err
        );

        httpd_stop(server);
        server = nullptr;
        serverReady = false;

        return false;
    }


    // ========================================
    // Register /api/v1/capture
    // ========================================

    httpd_uri_t captureUri = {};

    captureUri.uri      = "/api/v1/capture";
    captureUri.method   = HTTP_GET;
    captureUri.handler  = captureHandler;
    captureUri.user_ctx = nullptr;

    err = httpd_register_uri_handler(
        server,
        &captureUri
    );

    if (err != ESP_OK)
    {
        Serial.printf(
            "[HTTP] ERROR: Failed to register /api/v1/capture: 0x%X\n",
            err
        );

        httpd_stop(server);

        server = nullptr;
        serverReady = false;

        return false;
    }


    httpd_uri_t previewUri = {};
    previewUri.uri = "/";
    previewUri.method = HTTP_GET;
    previewUri.handler = previewHandler;
    if (httpd_register_uri_handler(server, &previewUri) != ESP_OK)
    {
        httpd_stop(server);
        server = nullptr;
        return false;
    }

    serverReady = true;

    Serial.printf(
        "[HTTP] Listening on port %d\n",
        HTTP_PORT
    );

    Serial.println("[HTTP] GET /health");
    Serial.println("[HTTP] GET /api/v1/status");

    return true;
}

bool ready()
{
    return serverReady;
}


void stop()
{
    if (server == nullptr)
    {
        return;
    }

    Serial.println("[HTTP] Stopping server...");

    httpd_stop(server);

    server = nullptr;
    serverReady = false;
}

}
