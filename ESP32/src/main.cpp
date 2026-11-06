#include <Arduino.h>

#include "config.h"
#include "camera/camera_service.h"
#include "network/wifi_service.h"
#include "http/http_server.h"
#include "mjpeg_stream.h"

void setup()
{
    Serial.begin(115200);
    delay(2000);

    Serial.println();
    Serial.println("============================");
    Serial.println(" ESP32-S3 Camera Node");
    Serial.println("============================");

    Serial.printf(
        "[BOOT] Device: %s\n",
        DEVICE_ID
    );

    Serial.printf(
        "[BOOT] Firmware: %s\n",
        DEVICE_VERSION
    );


    // ========================================
    // Camera
    // ========================================

    if (!CameraService::begin())
    {
        Serial.println(
            "[BOOT] ERROR: Camera failed"
        );

        return;
    }


    // ========================================
    // Wi-Fi
    // ========================================

    if (!WiFiService::begin())
    {
        Serial.println(
            "[BOOT] ERROR: Wi-Fi failed"
        );

        return;
    }


    // ========================================
    // HTTP
    // ========================================

    if (!HttpServer::begin())
    {
        Serial.println(
            "[BOOT] ERROR: HTTP server failed"
        );

        return;
    }

    if (!startMjpegServer()) {
        Serial.println("MJPEG server failed to start");
    }

    Serial.println("[HTTP] GET /health");
    Serial.println("[HTTP] GET /api/v1/status");
    Serial.println("[HTTP] GET /api/v1/capture");

    Serial.println();
    Serial.println("[BOOT] Device ready");

    Serial.printf(
        "[BOOT] Health: http://%s/health\n",
        WiFiService::ip().toString().c_str()
    );
}


void loop()
{
    delay(5000);

    Serial.printf(
        "[STATUS] WiFi=%s IP=%s RSSI=%d dBm FreeHeap=%u FreePSRAM=%u\n",
        WiFiService::connected() ? "OK" : "DOWN",
        WiFiService::ip().toString().c_str(),
        WiFiService::rssi(),
        ESP.getFreeHeap(),
        ESP.getFreePsram()
    );
}