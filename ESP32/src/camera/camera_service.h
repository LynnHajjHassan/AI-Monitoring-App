#pragma once

#include "esp_camera.h"

namespace CameraService
{
    bool begin();

    bool ready();

    camera_fb_t* capture();

    void release(camera_fb_t* frame);

    sensor_t* sensor();
}