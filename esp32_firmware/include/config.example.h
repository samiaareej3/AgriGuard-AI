// Copy to include/config.h and fill in. config.h is git-ignored: never commit credentials.
#pragma once

#define WIFI_SSID        "your-wifi"
#define WIFI_PASSWORD    "your-wifi-password"

// Backend base URL (no trailing slash). Use HTTPS + a reverse proxy outside the lab.
#define API_BASE_URL     "http://192.168.1.10:8000/api/v1"
// Token shown ONCE when registering the device in the dashboard (Devices -> Register hardware).
#define DEVICE_TOKEN     "agd_replace_me"
#define FIRMWARE_VERSION "esp32cam-0.1.0"

// Relay driving the pump. GPIO14 is free on the AI-Thinker board (avoid GPIO12: strapping pin).
#define RELAY_PIN        14
#define RELAY_ACTIVE_LOW true

// Hardware fail-safe: the pump can NEVER run longer than this, whatever the server says.
#define MAX_SPRAY_MS     10000
#define HEARTBEAT_MS     5000
#define POLL_MS          1000
// Capture & upload a leaf image every N ms (0 = only on demand / disabled).
#define CAPTURE_EVERY_MS 0
