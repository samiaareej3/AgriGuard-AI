# API overview (v1)

Base URL: `http://localhost:8000/api/v1`. Interactive docs: `/docs` (Swagger) and `/redoc`.
The OpenAPI document at `/api/v1/openapi.json` is the authoritative reference.

## Authentication

| Caller | Header | How to obtain |
|---|---|---|
| Dashboard users | `Authorization: Bearer <token>` | `POST /auth/login {username, password}` → `access_token` (default TTL 12 h) |
| Devices | `X-Device-Token: agd_…` | Returned **once** by `POST /devices` (or rotate-token) |
| WebSocket | `?token=<bearer token>` | Same bearer token |

Roles: **viewer** (read) < **operator** (scans, approvals, e-stop, simulator) < **admin** (policy, users,
e-stop reset, device deletion, token rotation).

## Errors

Every non-2xx response:

```json
{"error": {"code": "CONFLICT", "message": "Operation is COMPLETED, not awaiting approval",
           "details": null, "request_id": "9f1c2e…"}}
```

Common codes: `VALIDATION_ERROR` 422, `INVALID_IMAGE` 422, `UNSUPPORTED_MEDIA_TYPE` 415,
`PAYLOAD_TOO_LARGE` 413, `UNAUTHORIZED`/`INVALID_CREDENTIALS`/`DEVICE_UNAUTHORIZED` 401, `FORBIDDEN` 403,
`NOT_FOUND` 404, `CONFLICT` 409, `RATE_LIMITED` 429 (`details.retry_after_s`), `DATABASE_UNAVAILABLE` 503,
`INTERNAL_ERROR` 500 (no internals exposed). Every response carries `X-Request-ID` (send your own to
correlate logs).

## Endpoints

| Method & path | Role | Purpose |
|---|---|---|
| `GET /health`, `GET /health/ready` | none | Liveness; readiness with database/model components (503 if a critical one is down) |
| `POST /auth/login`, `GET /auth/me`, `POST /auth/change-password` | –/viewer | Session |
| `GET/POST /users` | admin | List / create users |
| `GET /devices`, `GET /devices/{id}` | viewer | Devices with derived connectivity |
| `POST /devices` | operator | Register hardware device → one-time token |
| `DELETE /devices/{id}`, `POST /devices/{id}/rotate-token` | admin | |
| `GET /devices/{id}/telemetry?minutes=`, `GET /devices/{id}/commands` | viewer | History |
| `GET /simulator/status`, `POST /simulator/devices`, `POST /simulator/devices/{id}/connection`, `PATCH /simulator/devices/{id}`, `POST /simulator/devices/{id}/scan` | viewer/operator | Simulator controls & fault injection |
| `POST /device/heartbeat`, `/device/disconnect`, `GET /device/commands/next`, `POST /device/commands/{id}/ack`, `/result`, `POST /device/scans` | device token | Device contract, see [DEVICE_API.md](DEVICE_API.md) |
| `POST /scans` (multipart `image`, optional `device_id`, `notes`) | operator | Classify + decide |
| `GET /scans?q=&label=&outcome=&device_id=&source=&date_from=&date_to=&page=&page_size=` | viewer | History |
| `GET /scans/{id}`, `GET /scans/{id}/image` | viewer | Detail / stored image |
| `GET /spray/operations?status=A,B&device_id=&page=` , `GET /spray/operations/{id}` | viewer | Operations |
| `POST /spray/operations/{id}/approve`, `/reject` (`{note}`) | operator | Approve re-evaluates all rules |
| `POST /spray/evaluate {scan_id, device_id?}` | viewer | Dry-run decision (no side effects) |
| `GET /spray/policy`, `PUT /spray/policy` | viewer / admin | Versioned policy (`expected_version` for concurrency) |
| `GET /safety/emergency-stop`, `POST /safety/emergency-stop {reason}`, `POST /safety/emergency-stop/reset {reason}` | viewer / operator / admin | E-stop |
| `GET /dashboard/summary`, `GET /analytics?days=1..90` | viewer | Aggregates from stored records |
| `GET /insights/weather`, `/insights/climate` (`?refresh=true`), `/insights/sources` | viewer | External data with provenance and freshness |
| `GET /logs?category=&level=&device_id=&page=`, `GET /events/recent`, `GET /system/info` | viewer | Audit log, recent events, configuration |
| `WS /ws/events?token=` | viewer | Real-time event stream |

### Example: scan from the command line

```powershell
$t = (Invoke-RestMethod -Method Post http://localhost:8000/api/v1/auth/login -ContentType application/json `
      -Body '{"username":"admin","password":"agriguard-dev"}').access_token
curl.exe -H "Authorization: Bearer $t" -F "image=@backend/sample_images/late_blight/late_blight_1.jpg;type=image/jpeg" `
     http://localhost:8000/api/v1/scans
```

### WebSocket event types

`scan.created`, `spray.updated`, `command.queued`, `device.heartbeat`, `device.connectivity`,
`device.updated`, `device.deleted`, `estop.changed`, `policy.updated`, `log.created`, plus `hello` / `ping`.
Each frame: `{"id","type","ts","simulated","data"}`.
