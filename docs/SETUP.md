# Setup, configuration and running

All commands are Windows PowerShell. Project root: `D:\AMAANz\Agri-Guard`.

## Prerequisites

| Tool | Version used | Notes |
|---|---|---|
| Python | **3.11.9** (`.venv`) | Do not use the system Python 3.14; TensorFlow does not support it. Always call `.venv\Scripts\python.exe`. |
| Node.js / npm | 24.16 / 11.13 | Frontend |
| Git | 2.54 | |
| PlatformIO (optional) | n/a | Only for flashing the ESP32 later |

## 1. Backend

```powershell
cd D:\AMAANz\Agri-Guard
# (only if .venv is missing)  py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt     # API + tests
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-ml.txt      # + TensorFlow for real inference (~600 MB)
Copy-Item backend\.env.example backend\.env                                  # optional, then edit
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

- Swagger UI: http://localhost:8000/docs · OpenAPI JSON: http://localhost:8000/api/v1/openapi.json
- Liveness `GET /api/v1/health`; readiness `GET /api/v1/health/ready` (database + model status)
- Without TensorFlow installed the API still runs; scans return `MODEL_UNAVAILABLE` → `REVIEW_REQUIRED`.

### Configuration (`backend/.env`)

| Variable | Default | Meaning |
|---|---|---|
| `ENVIRONMENT` | `development` | `production` enforces SECRET_KEY, non-default ADMIN_PASSWORD, no wildcard CORS |
| `MONGODB_URI` | *(empty)* | Empty = in-memory store (non-persistent, flagged in UI) |
| `DATABASE_NAME` | `agriguard_db` | |
| `SECRET_KEY` | random per process in dev | ≥32 chars in production; tokens invalidate on restart if unset |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / `agriguard-dev` (dev only) | First admin account, created once |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated allowlist |
| `MAX_UPLOAD_MB` | 5 | Upload size limit |
| `UPLOAD_RETENTION_DAYS` / `LOG_RETENTION_DAYS` | 30 / 90 | Image files / audit log retention |
| `MODEL_PATH` / `MODEL_CONFIG_PATH` | `ai_training/models/...` | Trained artefact + its config |
| `DEFAULT_CONFIDENCE_THRESHOLD` | 0.75 | Seeds the policy on first start (then edit in Settings) |
| `SIMULATOR_ENABLED` / `SIMULATOR_SEED_DEVICES` / `SIMULATOR_TICK_SECONDS` | true / 2 / 5 | Device simulator |
| `LOCATION_NAME` / `LOCATION_LAT` / `LOCATION_LON` | Hyderabad, Telangana | Weather location |
| `EXTERNAL_DATA_ENABLED` | true | Disable to run fully offline |
| `RATE_LIMIT_LOGIN_PER_MIN` / `..._UPLOAD_...` / `..._DEVICE_...` | 10 / 30 / 240 | In-process limits |

Spray **policy** (threshold, cooldown, durations, approval, weather rule…) is stored in the database and
edited in **Settings → Safety policy** (admin), versioned with optimistic concurrency.

## 2. MongoDB Atlas (free tier)

1. Create a **dedicated** Atlas project "AgriGuard" and a free M0 cluster.
2. *Database Access* → add user `agriguard_app` with role **readWrite on `agriguard_db` only** (least privilege).
3. *Network Access* → add **your current IP only**. Do not leave `0.0.0.0/0` enabled permanently.
4. *Connect → Drivers* → copy the `mongodb+srv://` string into `backend/.env` as `MONGODB_URI`
   (never commit it; `.env` is git-ignored).
5. Restart the API. `GET /api/v1/health/ready` should report `database: ok`; indexes (incl. TTL indexes for
   telemetry and logs) are created automatically.

If the cluster is unreachable the API still starts, readiness returns **503 `not_ready`**, data endpoints
return `503 DATABASE_UNAVAILABLE`, and PyMongo reconnects automatically. It never silently falls back to memory.
A local MongoDB (`mongodb://localhost:27017`) works the same way.

## 3. Frontend

```powershell
cd D:\AMAANz\Agri-Guard\frontend
npm install
Copy-Item .env.example .env.local     # only if the API is not at http://localhost:8000/api/v1
npm run dev                            # http://localhost:3000
# production build
npm run build; npm run start
```

`NEXT_PUBLIC_API_URL` is baked in at build time; rebuild after changing it, and add the frontend origin to
the backend's `CORS_ORIGINS`.

## 4. Model training (optional, artefact already included)

```powershell
cd D:\AMAANz\Agri-Guard\ai_training\dataset
git clone --depth 1 --filter=blob:none --sparse https://github.com/spMohanty/PlantVillage-Dataset.git plantvillage_src
cd plantvillage_src
git sparse-checkout set --no-cone "raw/color/Tomato___Early_blight/*" "raw/color/Tomato___Late_blight/*" "raw/color/Tomato___healthy/*" "leaf-map.json"
cd D:\AMAANz\Agri-Guard\ai_training\scripts
..\..\.venv\Scripts\python.exe prepare_dataset.py   # leakage-aware split (~1 min)
..\..\.venv\Scripts\python.exe train.py             # ~18 min on a laptop CPU
..\..\.venv\Scripts\python.exe evaluate.py          # metrics + plots + simulator samples
```

Or run `ai_training/notebooks/agriguard_training_colab.ipynb` on Colab/Kaggle.

## 5. Tests

```powershell
cd D:\AMAANz\Agri-Guard\backend;  ..\.venv\Scripts\python.exe -m pytest
cd D:\AMAANz\Agri-Guard\frontend; npm run lint; npm run typecheck; npm test
cd D:\AMAANz\Agri-Guard\frontend; npx playwright install chromium; npm run build; npm run test:e2e
# device contract against a running API (no hardware needed)
cd D:\AMAANz\Agri-Guard; .\.venv\Scripts\python.exe esp32_firmware\tools\device_contract_client.py --register --password agriguard-dev --image backend\sample_images\late_blight\late_blight_1.jpg --approve
```

The E2E suite reuses servers already on :8000/:3000, otherwise it starts them. It logs in with the dev
default password, so run it against a development backend.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Dashboard says "Cannot reach the AgriGuard API" | Backend not running on :8000, or `NEXT_PUBLIC_API_URL` wrong |
| CORS error in browser console | Add the frontend origin to `CORS_ORIGINS` |
| Scans say "Model unavailable" | Install `requirements-ml.txt`; wait for readiness `model: ok`; check `MODEL_PATH` |
| Logged out after backend restart | Expected in dev without `SECRET_KEY` (random per process) |
| Data disappears on restart | In-memory mode: set `MONGODB_URI` |
| `python` picks 3.14 | Use `.venv\Scripts\python.exe` explicitly |
