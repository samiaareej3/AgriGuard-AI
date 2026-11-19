# AgriGuard: Progress Log

## Current state (2026-11-18): all phases 0–10 implemented

| Phase | Status | Verification |
|---|---|---|
| 0 Repository audit | Done | See below |
| 1 Backend foundation | Done | settings, JSON logs + request IDs, error envelope, health/readiness |
| 2 MongoDB | Done (Atlas path unverified) | mongomock in tests/demo; unreachable-Atlas behaviour tested (503 not_ready). **Not run against a real Atlas cluster: no credentials provided** |
| 3 Device simulator + contract | Done | pytest + live HTTP run of `device_contract_client.py` (register → heartbeat → scan + idempotent retry → approve → SPRAY → ack ×2 → result → disconnect) |
| 4 AI pipeline | Done | PlantVillage tomato subset, leakage-aware split, MobileNetV2 trained on CPU (18 min); held-out test: 96.89 % accuracy, 0.966 macro-F1 (n = 644) |
| 5 Safety engine | Done | 30+ rule unit tests + API flow tests (cooldown, overlap race, e-stop, timeouts, re-evaluation at approval) |
| 6 Frontend foundation | Done | design tokens (light/dark), shell, auth, API client, realtime |
| 7 Dashboard workflows | Done | 9 pages + scan detail + login; all controls wired or disabled with a reason |
| 8 Real time & insights | Done | WebSocket stream; Open-Meteo + NASA POWER live, cached, provenance + freshness |
| 9 Integration & QA | Done | see test results |
| 10 Documentation | Done | README + docs/* |

### Test results (last run 2026-11-18)

| Suite | Command | Result |
|---|---|---|
| Backend (unit, API, flows, real model) | `..\.venv\Scripts\python.exe -m pytest` (in `backend/`) | **132 passed** |
| Frontend lint / types | `npm run lint`, `npm run typecheck` | clean |
| Frontend unit (Vitest + RTL) | `npm test` | **19 passed** |
| End-to-end (Playwright, real backend + model + prod build) | `npm run test:e2e` | **5 passed** (login redirect, all pages light/dark/mobile without errors or horizontal overflow, upload→prediction→decision, simulated capture→approve→spray completes→e-stop→reset, scan filters/detail) |
| Device contract over HTTP | `device_contract_client.py --register ... --approve` | full loop OK |
| Production build | `npm run build` | OK (13 routes) |

One harmless warning remains: Starlette suggests `httpx2` for its TestClient (install was blocked by the
session's permission policy; `httpx` works).

## Phase 0: audit findings (2026-11-18)

Empty scaffold, no commits/remote; `.venv` Python 3.11.9 (system also has 3.14). Fixed: UTF-16
`requirements.txt`, `.gitignore` `lib/` rule that would have hidden `frontend/lib/`, README DB mismatch.

## Key decisions

- **Routes** in `app/routes/`, schemas in `app/schemas/`; unused scaffold folders (`app/models`, `app/utils`,
  `backend/logs`) removed. Logs go to stdout (JSON) plus the `system_logs` collection.
- **In-memory fallback via mongomock** (same PyMongo API) when `MONGODB_URI` is unset, always disclosed in
  UI and readiness. Configured-but-down Atlas is never masked.
- **Auth:** stdlib scrypt + HMAC tokens, roles viewer/operator/admin; dev-only default admin password
  (rejected in production); device tokens hashed.
- **Command delivery by polling** (works behind NAT; same for simulator and ESP32).
- **Safety engine as a pure function** over an explicit snapshot; unknown = fail; re-evaluated at approval;
  atomic device lock against overlapping sprays.
- **Shared preprocessing module** imported by training and serving (no train/serve skew; verified that
  service output equals `model.predict`).
- **Group-wise split** using PlantVillage `leaf-map.json` + duplicate/near-duplicate detection.
- **Weather rule advisory by default** (configurable to blocking); engine uses cached data only.
- **Charts** use a CVD-validated palette (validator run in light and dark), table view on every chart, no
  dual axes.
- **shadcn/ui** added via its CLI. The CLI mis-resolved `@/lib/utils` to an unrelated npm package `cn`,
  which was removed and replaced with the standard `lib/utils.ts`.

## Known limitations / not verified

- **MongoDB Atlas** persistence is implemented but not exercised against a real cluster (needs a URI).
- **ESP32 firmware** is written but **not compiled or hardware-tested** (no PlatformIO toolchain/board here).
  Tank/battery sensors are absent, so on real hardware the safety engine will block spraying until they report.
- **Model**: lab-image metrics only; field accuracy unmeasured. OOD images can still get confident labels
  (mitigated by thresholds, quality heuristic, approval). Early Blight recall 93.8 % is the weakest class.
- Indian government data portals (data.gov.in, AGMARKNET, Telangana Open Data) were unreachable or not
  automatable at check time; Dataful terms unclear. See `DATA_SOURCES.md`.
- Bearer token in `localStorage`; per-process rate limiter (see `SECURITY.md`).
- Nothing has been committed to Git yet.

## Suggested next steps

1. Add an Atlas URI to `backend/.env` and run the app once to verify persistence/indexes.
2. Collect a small labelled **field** test set (ESP32-CAM or phone photos, plus PlantDoc tomato images) and
   measure domain shift before any field use.
3. Fit tank/battery sensors, compile and bench-test the firmware (water only) using the checklist in
   `ESP32_INTEGRATION.md`.
4. For deployment: httpOnly-cookie auth via a same-origin proxy, TLS reverse proxy with rate limits.
