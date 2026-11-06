#include "wifi_service.h"

#include "config.h"
#include "secrets.h"

namespace WiFiService
{

bool begin()
{
    Serial.printf(
        "[WIFI] Connecting to %s",
        WIFI_SSID
    );

    WiFi.mode(WIFI_STA);

    WiFi.setHostname(DEVICE_ID);

    WiFi.begin(
        WIFI_SSID,
        WIFI_PASSWORD
    );

    const unsigned long timeout = 15000;
    const unsigned long start = millis();

    while (WiFi.status() != WL_CONNECTED)
    {
        if (millis() - start >= timeout)
        {
            Serial.println();
            Serial.println("[WIFI] ERROR: Connection timeout");

            return false;
        }

        Serial.print(".");
        delay(500);
    }

    Serial.println();
    Serial.println("[WIFI] Connected");

    Serial.print("[WIFI] IP: ");
    Serial.println(WiFi.localIP());

    Serial.printf(
        "[WIFI] RSSI: %d dBm\n",
        WiFi.RSSI()
    );

    return true;
}


bool connected()
{
    return WiFi.status() == WL_CONNECTED;
}


IPAddress ip()
{
    return WiFi.localIP();
}


int32_t rssi()
{
    if (!connected())
    {
        return 0;
    }

    return WiFi.RSSI();
}

}