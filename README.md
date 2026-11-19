# AgriGuard

AI-assisted tomato-leaf disease detection with a **deterministic, independent spray-authorization (safety)
engine**, a real-time operations dashboard, and simulated ESP32-CAM devices that speak the same API contract
the real hardware will use.

> **A disease prediction never activates a pump by itself.** Every spray passes 13 explicit safety rules
> at scan time and again at operator approval, and an emergency stop is always one click away.
> The model is decision support, not a guaranteed field diagnosis.

| | |
|---|---|
| **Model** | MobileNetV2 transfer learning, 3 classes (Healthy / Early Blight / Late Blight), PlantVillage tomato subset |
| **Measured** | 96.9 % accuracy, 0.966 macro-F1 on 644 held-out test images (group-wise split by physical leaf), see [MODEL_CARD](docs/MODEL_CARD.md) |
| **Backend** | Python 3.11 · FastAPI · PyMongo (MongoDB Atlas or in-memory fallback) · WebSockets · 132 pytest tests |
| **Frontend** | Next.js 15 (App Router) · TypeScript · Tailwind 4 · shadcn/ui · TanStack Query · Recharts · 19 unit + 5 Playwright E2E tests |
| **Devices** | In-process simulator now; ESP32-CAM firmware + verified reference HTTP client for later |
| **Cost** | Everything runs locally on free/open-source tooling; external data from key-less public APIs |

## Quick start (Windows PowerShell)

Working directory: `D:\AMAANz\Agri-Guard`

```powershell
# 1. Backend (Python 3.11 venv already exists at .venv)
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt -r backend\requirements-ml.txt
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
#    -> http://localhost:8000/docs   (model loads in the background, ~30-60 s on first start)

# 2. Frontend (new terminal)
cd D:\AMAANz\Agri-Guard\frontend
npm install
npm run dev
#    -> http://localhost:3000   sign in: admin / agriguard-dev (development default only)
```

With no `backend\.env`, the API runs on an **in-memory database** (clearly flagged in the UI; data is lost on
restart) with two **simulated** devices. To persist data, set `MONGODB_URI` (see [docs/SETUP.md](docs/SETUP.md)).

## Running the tests

```powershell
cd D:\AMAANz\Agri-Guard\backend;  ..\.venv\Scripts\python.exe -m pytest          # 132 tests
cd D:\AMAANz\Agri-Guard\frontend; npm run lint; npm run typecheck; npm test     # lint, types, 19 unit tests
cd D:\AMAANz\Agri-Guard\frontend; npm run build; npm run test:e2e               # 5 end-to-end tests (starts both servers)
```

## What is in the box

- **Disease detection**: upload/camera capture → validated, EXIF-stripped image → MobileNetV2 → calibrated
  `CONFIDENT` / `UNCERTAIN` / `MODEL_UNAVAILABLE` result with probabilities, warnings, model version.
- **Safety engine**: pure function over an explicit snapshot (prediction, device, cooldown, active ops,
  e-stop, weather, approval). Unknown critical condition = fail. Outcomes: `REVIEW_REQUIRED`, `SKIP`,
  `BLOCKED`, `PENDING_APPROVAL`, `AUTHORIZED`. Full audit trail. See [docs/SAFETY.md](docs/SAFETY.md).
- **Spray operations**: approval queue, re-evaluation at approval, atomic device lock (no overlapping
  sprays), command queue with ack/result, timeouts, cooldown, emergency stop (operator) and reset (admin).
- **Devices**: registration with one-time tokens, heartbeats, telemetry, online/offline detection, simulator
  fault injection (signal loss, pump fault, ignored commands, low tank, sensor fault).
- **Dashboard**: Overview, Live Monitoring (WebSocket), Disease Detection, Scan History (filters/detail),
  Spray Operations, Devices, Analytics, Agricultural Insights (Open-Meteo + NASA POWER with freshness),
  Settings (policy, model card, users, audit log). Light/dark, responsive, keyboard accessible.

## Documentation

| Doc | Contents |
|---|---|
| [SETUP](docs/SETUP.md) | Install, configuration, MongoDB Atlas, running, testing, troubleshooting |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | Components, data flow, collections, design decisions |
| [API](docs/API.md) | REST/WebSocket overview, auth, errors (full OpenAPI at `/docs`) |
| [DEVICE_API](docs/DEVICE_API.md) | Versioned device contract v1: examples, retries, idempotency |
| [SAFETY](docs/SAFETY.md) | Rules, outcomes, operation lifecycle, emergency stop |
| [MODEL_CARD](docs/MODEL_CARD.md) | Data, training, measured metrics, limitations |
| [DATA_SOURCES](docs/DATA_SOURCES.md) | Every dataset/API investigated, licence, status |
| [SECURITY](docs/SECURITY.md) | Auth, uploads, secrets, rate limits, deployment checklist |
| [ESP32_INTEGRATION](docs/ESP32_INTEGRATION.md) | Wiring, firmware, swapping simulator for hardware |
| [DEMO_SCRIPT](docs/DEMO_SCRIPT.md) | 10-minute walkthrough |
| [PROGRESS](docs/PROGRESS.md) | Progress log, decisions, verification status, known limitations |

## Repository layout

```
backend/          FastAPI app (app/core, routes, schemas, services, adapters, db, ml), tests/, sample_images/
frontend/         Next.js dashboard (app/, components/, lib/, tests/unit, tests/e2e)
ai_training/      scripts/ (prepare_dataset, train, evaluate), models/ (trained artefact), reports/, notebooks/
esp32_firmware/   PlatformIO project (src/main.cpp) + tools/device_contract_client.py
docs/             Documentation
```

## Status and honesty notes

- Hardware is **not** connected yet. All device telemetry and spray operations in the demo are **simulated**
  and labelled as such everywhere. The ESP32 firmware is written to the contract but has **not been compiled
  or run on hardware**.
- Model metrics are from PlantVillage lab images. **Field accuracy has not been measured** and is expected to
  be lower.
- For any physical demonstration use **water only** unless your institution approved another procedure.
  AgriGuard does not provide chemical dosing or pesticide-use guidance.

Dataset credit: PlantVillage, Mohanty, Hughes & Salathé (2016), CC BY-SA 3.0. Weather data by
Open-Meteo.com (CC BY 4.0). Climate data from the NASA Langley Research Center POWER Project.
