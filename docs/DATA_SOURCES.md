# Data sources investigated

Checked on **2026-11-18** from the development machine (HTTP status in brackets). Nothing was scraped in
breach of terms. The same list is served by `GET /api/v1/insights/sources` and shown on the Insights page.

## Integrated

| Source | Use | Licence / terms | Notes |
|---|---|---|---|
| **PlantVillage** (GitHub `spMohanty/PlantVillage-Dataset`) [200] | Model training/evaluation; 12 test images as simulator samples | CC BY-SA 3.0 (HF dataset card `mohanty/PlantVillage`); cite Mohanty et al. 2016 | Includes `leaf-map.json` (leaf IDs) used for leakage-free splits |
| **Open-Meteo Forecast API** [200] | Current conditions, 7-day forecast, spray weather rule, blight heuristic | CC BY 4.0; free for non-commercial use, < 10,000 calls/day, no key | Attribution "Weather data by Open-Meteo.com". Cached 30 min |
| **NASA POWER daily point API** (community AG) [200] | Last ~30 days temperature, humidity, rainfall, solar radiation | NASA open data; acknowledge NASA LaRC POWER Project | No key needed. Daily data lags a few days; fill values (−999) shown as missing |

## Investigated, not integrated

| Source | Result | Decision |
|---|---|---|
| Hugging Face PlantVillage | Reachable; same data/licence | GitHub sparse checkout chosen (lets us take only 3 classes + leaf map, ~75 MB) |
| TensorFlow Datasets `plant_village` | Documented; 828 MB download from Mendeley mirror, no leaf grouping | Not needed |
| PlantDoc / Kaggle / Mendeley candidates | Field-style datasets exist but licences vary per upload and Kaggle needs an account/API key | Recommended next step: a **field test set** (PlantDoc tomato classes) to measure domain shift. Not used yet |
| **Dataful** (Factly), Telangana search [200] | Lists Telangana cropped-area (2013-14 to 2023-24) and soil-health datasets; some marked "Exclusive"; pricing page; no documented public API; terms unclear | Not redistributed. Could be downloaded manually under its terms for a report |
| Open Government Data Platform India (data.gov.in) [503; API timed out] | Requires a free API key | Unavailable at check time. Integration path: add `DATA_GOV_IN_API_KEY` later for mandi prices/crop statistics |
| AGMARKNET [403 to automated requests] | No documented open API | Not scraped |
| Telangana Open Data [timeout] | Unreachable at check time | Not integrated |
| India Meteorological Department [200] | Website reachable; no key-less open JSON API verified | Open-Meteo used instead |
| ICAR [200] | Reference material, no data API | Reference only |
| NASA Earthdata [200] | Requires Earthdata login; heavy raster products | Out of scope for the prototype |

## Rules the app follows

- Every external value in the UI shows **source, retrieval time and freshness** (`live`, `stale (cached)`, `unavailable`).
- Failed refreshes serve the last good response **labelled stale**; with no cache the UI shows an
  explicit *unavailable* state. Values are never invented.
- The safety engine reads only the cached forecast (≤ 3 h old) and never waits on the network; missing
  weather is "unknown" (advisory warning by default, blocking if configured).
