#pragma once

#include "esp_camera.h"

// ==============================
// Device
// ==============================

#define DEVICE_ID       "cam-01"
#define DEVICE_VERSION  "0.3.0"

// ==============================
// Camera
// ==============================

#define CAMERA_XCLK_FREQ       10000000
#define CAMERA_FRAME_SIZE      FRAMESIZE_VGA
#define CAMERA_RESOLUTION_NAME "640x480"
#define CAMERA_JPEG_QUALITY    12
#define CAMERA_FB_COUNT        2
// Adjust to the physical camera mounting; applied to the JPEG at the sensor.
#define CAMERA_VFLIP           1
#define CAMERA_HMIRROR         1

// ==============================
// HTTP
// ==============================

#define HTTP_PORT 80
