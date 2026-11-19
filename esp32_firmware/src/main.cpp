// AgriGuard ESP32-CAM firmware — implements the device <-> backend contract v1 (docs/DEVICE_API.md).
//
// STATUS: written to the same contract as the verified Python reference client
// (tools/device_contract_client.py) but NOT yet compiled or tested on hardware.
//
// SAFETY DESIGN
//  * The device never decides to spray. It only executes SPRAY commands that the
//    backend's safety engine authorized and an operator approved.
//  * Hard cap: the relay can never stay on longer than MAX_SPRAY_MS (local timer).
//  * Relay is forced OFF on boot, on STOP, when the server reports emergency stop,
//    and when Wi-Fi/backend contact is lost during a spray.
//  * Use WATER ONLY for demonstrations unless your institution approved otherwise.

#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "esp_camera.h"
#include "config.h"

// ---- AI-Thinker ESP32-CAM pin map (OV2640) ----
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22

static String currentCommandId = "";
static unsigned long pumpStartedAt = 0;
static unsigned long pumpDurationMs = 0;
static bool pumpOn = false;
static bool emergencyStop = false;
static unsigned long lastHeartbeat = 0, lastPoll = 0, lastCapture = 0, lastServerContact = 0;

// ---------------------------------------------------------------- relay
void relayWrite(bool on) {
  digitalWrite(RELAY_PIN, (on ^ RELAY_ACTIVE_LOW) ? HIGH : LOW);
  pumpOn = on;
}

void pumpStop() { relayWrite(false); pumpDurationMs = 0; }

// ---------------------------------------------------------------- http helpers
int apiRequest(const char* method, const String& path, const String& body, String& response) {
  if (WiFi.status() != WL_CONNECTED) return -1;
  HTTPClient http;
  http.setTimeout(10000);
  http.begin(String(API_BASE_URL) + path);
  http.addHeader("X-Device-Token", DEVICE_TOKEN);
  if (body.length()) http.addHeader("Content-Type", "application/json");
  int code = http.sendRequest(method, body);
  response = code > 0 ? http.getString() : "";
  http.end();
  if (code > 0) lastServerContact = millis();
  return code;
}

// Retries idempotent calls (ack/result are idempotent server-side) with backoff.
int apiRequestRetry(const char* method, const String& path, const String& body, String& response, int tries = 3) {
  int code = -1;
  for (int i = 0; i < tries; i++) {
    code = apiRequest(method, path, body, response);
    if (code > 0 && code < 500 && code != 429) return code;
    delay(500 * (1 << i));
  }
  return code;
}

// ---------------------------------------------------------------- camera
bool cameraInit() {
  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0; c.ledc_timer = LEDC_TIMER_0;
  c.pin_d0 = Y2_GPIO_NUM; c.pin_d1 = Y3_GPIO_NUM; c.pin_d2 = Y4_GPIO_NUM; c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM; c.pin_d5 = Y7_GPIO_NUM; c.pin_d6 = Y8_GPIO_NUM; c.pin_d7 = Y9_GPIO_NUM;
  c.pin_xclk = XCLK_GPIO_NUM; c.pin_pclk = PCLK_GPIO_NUM; c.pin_vsync = VSYNC_GPIO_NUM; c.pin_href = HREF_GPIO_NUM;
  c.pin_sccb_sda = SIOD_GPIO_NUM; c.pin_sccb_scl = SIOC_GPIO_NUM; c.pin_pwdn = PWDN_GPIO_NUM; c.pin_reset = RESET_GPIO_NUM;
  c.xclk_freq_hz = 20000000; c.pixel_format = PIXFORMAT_JPEG;
  c.frame_size = psramFound() ? FRAMESIZE_VGA : FRAMESIZE_QVGA;  // 640x480 is plenty for a 224px model
  c.jpeg_quality = 12; c.fb_count = psramFound() ? 2 : 1;
  return esp_camera_init(&c) == ESP_OK;
}

// POST /device/scans (multipart, field "image") with an Idempotency-Key so retries never duplicate.
bool captureAndUpload() {
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) return false;
  String key = String((uint32_t)ESP.getEfuseMac(), HEX) + "-" + String(millis());
  String boundary = "agriguardboundary";
  String head = "--" + boundary + "\r\nContent-Disposition: form-data; name=\"image\"; filename=\"capture.jpg\"\r\n"
                "Content-Type: image/jpeg\r\n\r\n";
  String tail = "\r\n--" + boundary + "--\r\n";
  size_t total = head.length() + fb->len + tail.length();
  uint8_t* buf = (uint8_t*)ps_malloc(total);
  if (!buf) { esp_camera_fb_return(fb); return false; }
  memcpy(buf, head.c_str(), head.length());
  memcpy(buf + head.length(), fb->buf, fb->len);
  memcpy(buf + head.length() + fb->len, tail.c_str(), tail.length());
  esp_camera_fb_return(fb);

  int code = -1;
  for (int i = 0; i < 3 && (code <= 0 || code >= 500); i++) {
    HTTPClient http;
    http.setTimeout(20000);
    http.begin(String(API_BASE_URL) + "/device/scans");
    http.addHeader("X-Device-Token", DEVICE_TOKEN);
    http.addHeader("Idempotency-Key", key);
    http.addHeader("Content-Type", "multipart/form-data; boundary=" + boundary);
    code = http.POST(buf, total);
    http.end();
    if (code <= 0 || code >= 500) delay(1000 * (1 << i));
  }
  free(buf);
  Serial.printf("[scan] upload -> HTTP %d\n", code);
  return code == 200 || code == 201;
}

// ---------------------------------------------------------------- protocol
void sendHeartbeat() {
  JsonDocument doc;
  doc["status"] = "ok";
  doc["firmware_version"] = FIRMWARE_VERSION;
  doc["uptime_s"] = millis() / 1000.0;
  JsonObject t = doc["telemetry"].to<JsonObject>();
  t["rssi_dbm"] = WiFi.RSSI();
  t["pump_state"] = pumpOn ? "running" : "idle";
  // Tank level / battery sensors are not fitted yet: leave them out (null = unknown).
  // The safety engine treats unknown health values as a FAILURE, so spraying will be
  // blocked until real sensors report them. That is intentional (fail-safe).
  String body, resp;
  serializeJson(doc, body);
  int code = apiRequest("POST", "/device/heartbeat", body, resp);
  if (code == 200) {
    JsonDocument r;
    if (!deserializeJson(r, resp)) {
      emergencyStop = r["emergency_stop_active"] | false;
      if (emergencyStop && pumpOn) { pumpStop(); Serial.println("[safety] e-stop reported: pump OFF"); }
    }
  }
  Serial.printf("[heartbeat] HTTP %d\n", code);
}

void reportResult(const String& id, bool ok, const char* msg, float seconds) {
  JsonDocument doc;
  doc["success"] = ok; doc["message"] = msg; doc["actual_duration_s"] = seconds;
  String body, resp;
  serializeJson(doc, body);
  apiRequestRetry("POST", "/device/commands/" + id + "/result", body, resp);
}

void pollCommand() {
  String resp;
  int code = apiRequest("GET", "/device/commands/next", "", resp);
  if (code != 200) return;  // 204 = nothing to do
  JsonDocument cmd;
  if (deserializeJson(cmd, resp)) return;
  String id = cmd["id"].as<String>();
  String type = cmd["type"].as<String>();
  String ackResp;
  apiRequestRetry("POST", "/device/commands/" + id + "/ack", "", ackResp);

  if (type == "STOP") {
    if (pumpOn && currentCommandId.length()) {
      reportResult(currentCommandId, false, "Stopped by STOP command", (millis() - pumpStartedAt) / 1000.0);
    }
    pumpStop();
    currentCommandId = "";
    reportResult(id, true, "Pump stopped", 0);
    return;
  }
  if (type == "SPRAY") {
    if (id == currentCommandId) return;  // re-delivery of the command already running
    if (emergencyStop) { reportResult(id, false, "Refused: emergency stop active", 0); return; }
    float seconds = cmd["params"]["duration_s"] | 0.0f;
    unsigned long ms = (unsigned long)(seconds * 1000);
    if (ms == 0) { reportResult(id, false, "Invalid duration", 0); return; }
    if (ms > MAX_SPRAY_MS) ms = MAX_SPRAY_MS;  // hardware cap wins over any server value
    currentCommandId = id;
    pumpDurationMs = ms;
    pumpStartedAt = millis();
    relayWrite(true);
    Serial.printf("[spray] %s for %lu ms\n", id.c_str(), ms);
  }
}

void servicePump() {
  if (!pumpOn) return;
  unsigned long elapsed = millis() - pumpStartedAt;
  bool lostContact = millis() - lastServerContact > 3UL * HEARTBEAT_MS;
  if (elapsed >= pumpDurationMs || elapsed >= MAX_SPRAY_MS || lostContact) {
    pumpStop();
    if (currentCommandId.length()) {
      reportResult(currentCommandId, !lostContact, lostContact ? "Aborted: lost backend contact" : "Spray completed",
                   elapsed / 1000.0);
      currentCommandId = "";
    }
  }
}

// ---------------------------------------------------------------- arduino
void setup() {
  pinMode(RELAY_PIN, OUTPUT);
  relayWrite(false);  // fail-safe default
  Serial.begin(115200);
  if (!cameraInit()) Serial.println("[camera] init FAILED (scans disabled)");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("[wifi] connecting");
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) { delay(500); Serial.print("."); }
  Serial.printf("\n[wifi] %s\n", WiFi.status() == WL_CONNECTED ? WiFi.localIP().toString().c_str() : "not connected");
  lastServerContact = millis();
}

void loop() {
  servicePump();  // always first: enforces the duration cap
  if (WiFi.status() != WL_CONNECTED) {
    if (pumpOn) pumpStop();
    WiFi.reconnect();
    delay(1000);
    return;
  }
  unsigned long now = millis();
  if (now - lastHeartbeat >= HEARTBEAT_MS) { lastHeartbeat = now; sendHeartbeat(); }
  if (now - lastPoll >= POLL_MS) { lastPoll = now; pollCommand(); }
  if (CAPTURE_EVERY_MS > 0 && now - lastCapture >= CAPTURE_EVERY_MS) { lastCapture = now; captureAndUpload(); }
  delay(20);
}
