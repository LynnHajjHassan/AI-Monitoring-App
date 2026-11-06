#pragma once

#include <Arduino.h>
#include <WiFi.h>

namespace WiFiService
{
    bool begin();

    bool connected();

    IPAddress ip();

    int32_t rssi();
}