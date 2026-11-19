# Device ↔ backend contract, version 1

Used by **both** the in-process simulator (via `DeviceGateway`) and real ESP32-CAM firmware (via HTTP).
Verified end to end over HTTP with `esp32_firmware/tools/device_contract_client.py`.

- Base: `http://<host>:8000/api/v1/device` (use HTTPS through a reverse proxy outside a lab network)
- Auth: header `X-Device-Token: agd_…` (issued once at registration; only a SHA-256 hash is stored)
- Content type: JSON unless stated; timestamps ISO-8601 **UTC**
- Devices never talk to MongoDB and never decide to spray.
- Rate limit: 240 requests/min per device (HTTP 429 with `retry_after_s`)

## Loop

```
every 5 s   POST /heartbeat            (status + telemetry)  → learn emergency_stop_active
every 1 s   GET  /commands/next        204 = nothing, 200 = command
on command  POST /commands/{id}/ack    then execute (bounded by local MAX_SPRAY_MS)
when done   POST /commands/{id}/result {success, message, actual_duration_s}
on capture  POST /scans                multipart image + Idempotency-Key
shutdown    POST /disconnect           (optional, marks offline immediately)
```

## Endpoints

### `POST /heartbeat`
```json
{"status": "ok", "firmware_version": "esp32cam-0.1.0", "uptime_s": 312.5,
 "telemetry": {"temperature_c": 27.4, "humidity_pct": 61, "battery_pct": 88,
               "tank_level_pct": 72, "rssi_dbm": -63, "pump_state": "idle"}}
```
All telemetry fields are optional/nullable. **Unknown values must be sent as null or omitted, never guessed.**
The safety engine treats unknown tank/battery/status as a failure (fail-safe). Ranges are validated
(e.g. `battery_pct` 0–100), out-of-range → 422.

Response `200`:
```json
{"server_time": "2026-11-18T11:25:53.251Z", "device_id": "dev_…", "pending_commands": 1,
 "emergency_stop_active": false, "next_heartbeat_s": 5.0}
```
A device is **online** while heartbeats arrive within the policy's `device_offline_timeout_s` (default 30 s).

### `GET /commands/next`
`204` if nothing pending, else `200`:
```json
{"id": "cmd_3d25c6…", "device_id": "dev_…", "type": "SPRAY",
 "params": {"duration_s": 3.0, "operation_id": "op_5c6e…"}, "status": "DELIVERED",
 "created_at": "…", "expires_at": "…"}
```
- `STOP` is always delivered before `SPRAY`.
- Delivery is **at-least-once**: an un-acknowledged command is re-delivered. De-duplicate by `id`.
- Commands expire (`expires_at` = created + `command_ack_timeout_s`, default 20 s). An expired SPRAY fails
  its operation server-side and must not be executed.

### `POST /commands/{id}/ack`  (idempotent)
Acknowledge before actuating. Repeating returns `200` with the current state. Acking another device's
command → `404`.

### `POST /commands/{id}/result`  (idempotent)
```json
{"success": true, "message": "Spray completed", "actual_duration_s": 3.0}
```
`success: false` for faults, STOP-interrupted sprays, refusals (e.g. e-stop). Repeats return `200` unchanged.

### `POST /scans`
`multipart/form-data`, field **`image`** (JPEG/PNG/WebP, ≤ 5 MB, ≥ 64 px). Header
`Idempotency-Key: <unique per capture, [A-Za-z0-9._:-]{1,64}>`.
- `201` + scan record on first upload; **`200` + the same record** when retried with the same key.
- The response contains `prediction` and `decision`. The device does **not** act on them; it only executes
  commands.

### `POST /disconnect` → `204`

## Error codes

| HTTP | code | Device action |
|---|---|---|
| 401 | `DEVICE_UNAUTHORIZED` | Token invalid/rotated/device deleted: stop and alert |
| 404 | `NOT_FOUND` | Unknown command for this device: drop it |
| 413/415/422 | upload/validation errors | Do not retry unchanged |
| 429 | `RATE_LIMITED` | Back off `retry_after_s` |
| 503 | `DATABASE_UNAVAILABLE` | Retry with exponential backoff |

## Retry rules

- Safe to retry: heartbeat, ack, result, scans (with the same `Idempotency-Key`), commands/next.
- Back off 0.5 s, 1 s, 2 s… on network errors / 5xx / 429.
- If backend contact is lost **during a spray**, switch the pump off locally and report
  `success: false, "Aborted: lost backend contact"` when reconnected.

## Versioning

Path version `/api/v1`. Additive fields may appear in responses; devices must ignore unknown fields.
Breaking changes will ship as `/api/v2` alongside v1.
