#include "camera_service.h"

#include <Arduino.h>

#include "camera_pins.h"
#include "config.h"

namespace
{
    bool cameraReady = false;
}

namespace CameraService
{

bool begin()
{
    Serial.println("[CAMERA] Initializing...");

    if (!psramFound())
    {
        Serial.println("[CAMERA] ERROR: PSRAM not found");
        return false;
    }

    Serial.printf(
        "[CAMERA] PSRAM: %.2f MB\n",
        ESP.getPsramSize() / 1048576.0
    );

    camera_config_t config = {};

    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer   = LEDC_TIMER_0;

    // Camera data pins
    config.pin_d0 = CAM_PIN_D0;
    config.pin_d1 = CAM_PIN_D1;
    config.pin_d2 = CAM_PIN_D2;
    config.pin_d3 = CAM_PIN_D3;
    config.pin_d4 = CAM_PIN_D4;
    config.pin_d5 = CAM_PIN_D5;
    config.pin_d6 = CAM_PIN_D6;
    config.pin_d7 = CAM_PIN_D7;

    // Camera clock/sync
    config.pin_xclk  = CAM_PIN_XCLK;
    config.pin_pclk  = CAM_PIN_PCLK;
    config.pin_vsync = CAM_PIN_VSYNC;
    config.pin_href  = CAM_PIN_HREF;

    // SCCB
    config.pin_sccb_sda = CAM_PIN_SIOD;
    config.pin_sccb_scl = CAM_PIN_SIOC;

    // Power/reset
    config.pin_pwdn  = CAM_PIN_PWDN;
    config.pin_reset = CAM_PIN_RESET;

    // Camera settings
    config.xclk_freq_hz = CAMERA_XCLK_FREQ;

    config.pixel_format = PIXFORMAT_JPEG;
    config.frame_size   = CAMERA_FRAME_SIZE;

    config.jpeg_quality = CAMERA_JPEG_QUALITY;

    config.fb_count    = CAMERA_FB_COUNT;
    config.fb_location = CAMERA_FB_IN_PSRAM;

    config.grab_mode = CAMERA_GRAB_LATEST;

    esp_err_t err = esp_camera_init(&config);

    if (err != ESP_OK)
    {
        Serial.printf(
            "[CAMERA] ERROR: initialization failed: 0x%X\n",
            err
        );

        cameraReady = false;
        return false;
    }

    sensor_t* s = esp_camera_sensor_get();

    if (s == nullptr || s->set_vflip(s, CAMERA_VFLIP) != 0 ||
        s->set_hmirror(s, CAMERA_HMIRROR) != 0)
    {
        Serial.println("[CAMERA] ERROR: Could not configure orientation");
        esp_camera_deinit();
        cameraReady = false;
        return false;
    }

    cameraReady = true;
    Serial.printf("[CAMERA] Vertical flip=%d Horizontal mirror=%d\n",
                  CAMERA_VFLIP, CAMERA_HMIRROR);

    if (s != nullptr)
    {
        Serial.printf(
            "[CAMERA] Sensor PID: 0x%04X\n",
            s->id.PID
        );
    }

    Serial.println("[CAMERA] Ready");

    return true;
}


bool ready()
{
    return cameraReady;
}


camera_fb_t* capture()
{
    if (!cameraReady)
    {
        return nullptr;
    }

    return esp_camera_fb_get();
}


void release(camera_fb_t* frame)
{
    if (frame != nullptr)
    {
        esp_camera_fb_return(frame);
    }
}


sensor_t* sensor()
{
    if (!cameraReady)
    {
        return nullptr;
    }

    return esp_camera_sensor_get();
}

}
