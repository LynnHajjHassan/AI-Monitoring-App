#pragma once

// Starts an independent MJPEG HTTP server on TCP port 81.
// Call once AFTER camera init, Wi-Fi connect and the existing port-80 API startup.
// Existing /health, /api/v1/status and /api/v1/capture handlers are not modified.
bool startMjpegServer();
