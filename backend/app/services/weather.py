"""Agricultural/weather context from free, key-less public APIs.

* Open-Meteo forecast API (CC BY 4.0, non-commercial free tier) — current
  conditions + 7-day forecast; also feeds the safety engine's weather rule.
* NASA POWER daily point API (Agroclimatology community) — last ~30 days.

Responses are cached in memory and persisted to ``weather_records``. On
failure the last good response is served and explicitly marked as cached/stale
with its retrieval time; if nothing is cached the API returns an
``unavailable`` state. Values are never invented.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.parse
import urllib.request
from datetime import timedelta
from typing import Any

from pymongo.errors import PyMongoError

from app.core.config import Settings
from app.core.timeutil import ensure_utc, new_id, utcnow
from app.db.client import Database
from app.services.safety import WeatherSnapshot

logger = logging.getLogger("agriguard.weather")

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
USER_AGENT = "AgriGuard/1.0 (educational precision-agriculture prototype)"

SOURCES: list[dict[str, Any]] = [
    {"id": "open_meteo", "name": "Open-Meteo Forecast API", "url": "https://open-meteo.com/en/docs",
     "license": "CC BY 4.0 (free tier for non-commercial use; <10k calls/day)",
     "attribution": "Weather data by Open-Meteo.com", "status": "integrated",
     "used_for": "Current conditions, 7-day forecast, spray weather rule"},
    {"id": "nasa_power", "name": "NASA POWER (Agroclimatology)", "url": "https://power.larc.nasa.gov/",
     "license": "NASA open data; cite NASA Langley Research Center POWER Project",
     "attribution": "Data from the NASA Langley Research Center (LaRC) POWER Project funded through the "
                    "NASA Earth Science/Applied Science Program.",
     "status": "integrated", "used_for": "Recent 30-day temperature, rainfall, humidity, solar radiation"},
    {"id": "plantvillage", "name": "PlantVillage dataset (tomato subset)",
     "url": "https://github.com/spMohanty/PlantVillage-Dataset", "license": "CC BY-SA 3.0",
     "attribution": "Mohanty, Hughes & Salathé (2016), Frontiers in Plant Science 7:1419",
     "status": "integrated", "used_for": "Model training and evaluation"},
    {"id": "data_gov_in", "name": "Open Government Data Platform India", "url": "https://www.data.gov.in/",
     "license": "Government Open Data License – India", "status": "not_integrated",
     "used_for": "Candidate: district crop statistics, mandi prices (requires free API key)",
     "note": "Portal returned HTTP 503 and the API timed out when checked on 2026-11-18."},
    {"id": "agmarknet", "name": "AGMARKNET", "url": "https://agmarknet.gov.in/", "status": "not_integrated",
     "license": "Government of India", "used_for": "Candidate: market prices",
     "note": "Returned HTTP 403 to automated requests; no documented open API. Not scraped (terms)."},
    {"id": "telangana_open_data", "name": "Telangana Open Data", "url": "https://data.telangana.gov.in/",
     "status": "not_integrated", "license": "Telangana Open Data policy",
     "note": "Connection timed out when checked on 2026-11-18."},
    {"id": "dataful", "name": "Dataful (Factly) – Telangana search", "url": "https://dataful.in/",
     "status": "not_integrated", "license": "Per-dataset terms; some datasets paid/exclusive",
     "note": "Reachable; lists Telangana cropped-area and soil-health datasets, but no documented public "
             "API and licensing is unclear, so data is not redistributed here."},
    {"id": "imd", "name": "India Meteorological Department", "url": "https://mausam.imd.gov.in/",
     "status": "not_integrated", "license": "IMD terms",
     "note": "Website reachable; no open, key-less JSON API verified for this project."},
    {"id": "icar", "name": "ICAR", "url": "https://icar.org.in/", "status": "reference",
     "license": "ICAR terms", "note": "Reference for agronomic guidance; no data API integrated."},
]


def _fetch_json(url: str, params: dict[str, Any], timeout: float) -> dict:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https hosts
        return json.loads(resp.read().decode("utf-8"))


class WeatherService:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self._cache: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._fetchers = {"forecast": self._fetch_forecast, "climate": self._fetch_climate}

    # -- fetchers -------------------------------------------------------------------
    def _fetch_forecast(self) -> dict:
        s = self.settings
        raw = _fetch_json(OPEN_METEO_URL, {
            "latitude": s.location_lat, "longitude": s.location_lon, "timezone": "auto", "forecast_days": 7,
            "current": "temperature_2m,relative_humidity_2m,precipitation,rain,wind_speed_10m,wind_gusts_10m,"
                       "weather_code,cloud_cover",
            "hourly": "temperature_2m,relative_humidity_2m,precipitation_probability,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,"
                     "wind_speed_10m_max,et0_fao_evapotranspiration,weather_code",
        }, s.external_http_timeout_s)
        hourly = raw.get("hourly", {})
        # Next 3 hours of precipitation probability for the spray rule.
        now_local = raw.get("current", {}).get("time")
        times = hourly.get("time", [])
        start = next((i for i, t in enumerate(times) if now_local and t >= now_local[:13]), 0)
        next_pp = [v for v in hourly.get("precipitation_probability", [])[start:start + 3] if v is not None]
        # Simple, clearly-labelled heuristic (not a validated disease model): count
        # forecast hours that are humid (RH >= 90%) and mild (10-25 °C), conditions
        # generally described as favourable for late blight.
        risk_hours = sum(
            1 for t, rh in zip(hourly.get("temperature_2m", []), hourly.get("relative_humidity_2m", []))
            if t is not None and rh is not None and rh >= 90 and 10 <= t <= 25
        )
        return {
            "location": {"name": s.location_name, "lat": raw.get("latitude"), "lon": raw.get("longitude"),
                         "elevation_m": raw.get("elevation"), "timezone": raw.get("timezone")},
            "current": raw.get("current", {}),
            "current_units": raw.get("current_units", {}),
            "next_3h_max_precipitation_probability": max(next_pp) if next_pp else None,
            "daily": raw.get("daily", {}),
            "daily_units": raw.get("daily_units", {}),
            "hourly": {k: hourly.get(k, [])[start:start + 48] for k in
                       ("time", "temperature_2m", "relative_humidity_2m", "precipitation_probability",
                        "wind_speed_10m")},
            "blight_favourable_hours_7d": risk_hours,
            "blight_heuristic_note": "Heuristic count of forecast hours with RH ≥ 90% and 10–25 °C. "
                                     "Indicative only; not a validated disease-risk model.",
        }

    def _fetch_climate(self) -> dict:
        s = self.settings
        end = (utcnow() - timedelta(days=1)).date()
        start = end - timedelta(days=30)
        raw = _fetch_json(NASA_POWER_URL, {
            "parameters": "T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,RH2M,ALLSKY_SFC_SW_DWN",
            "community": "AG", "latitude": s.location_lat, "longitude": s.location_lon,
            "start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d"), "format": "JSON",
        }, max(s.external_http_timeout_s, 20))
        params = raw.get("properties", {}).get("parameter", {})
        fill = raw.get("header", {}).get("fill_value", -999)
        days = sorted(next(iter(params.values()), {}).keys()) if params else []
        series = []
        for d in days:
            row = {"date": f"{d[:4]}-{d[4:6]}-{d[6:]}"}
            for key in params:
                v = params[key].get(d)
                row[key] = None if v is None or v == fill or v <= -990 else v
            series.append(row)
        series = [r for r in series if any(r[k] is not None for k in params)]  # drop not-yet-processed days
        units = {k: v.get("units") for k, v in raw.get("parameters", {}).items()}
        return {"location": {"name": s.location_name, "lat": s.location_lat, "lon": s.location_lon},
                "series": series, "units": units, "latest_available_date": series[-1]["date"] if series else None}

    # -- cache ---------------------------------------------------------------------
    def get(self, kind: str, force: bool = False) -> dict:
        ttl = timedelta(minutes=self.settings.weather_cache_minutes)
        source = "open_meteo" if kind == "forecast" else "nasa_power"
        with self._lock:
            cached = self._cache.get(kind) or self._load_persisted(kind)
        if cached and not force and utcnow() - cached["fetched_at"] < ttl:
            return self._envelope(cached, "live" if utcnow() - cached["fetched_at"] < ttl else "cached")
        if not self.settings.external_data_enabled:
            return self._envelope(cached, "stale", error="External data disabled") if cached else \
                self._unavailable(source, "External data disabled by configuration")
        try:
            data = self._fetchers[kind]()
            record = {"kind": kind, "source": source, "fetched_at": utcnow(), "data": data}
            with self._lock:
                self._cache[kind] = record
            try:
                self.db.weather_records.insert_one({"_id": new_id("wx"), "key": kind, **record})
            except PyMongoError:
                pass
            return self._envelope(record, "live")
        except Exception as exc:  # noqa: BLE001 - network/parse errors are expected
            logger.warning("external data fetch failed", extra={"kind": kind, "error": type(exc).__name__})
            if cached:
                return self._envelope(cached, "stale", error=f"Refresh failed ({type(exc).__name__})")
            return self._unavailable(source, f"Source unreachable ({type(exc).__name__})")

    def _load_persisted(self, kind: str) -> dict | None:
        try:
            doc = self.db.weather_records.find_one({"key": kind}, sort=[("fetched_at", -1)])
        except PyMongoError:
            return None
        if not doc:
            return None
        doc["fetched_at"] = ensure_utc(doc["fetched_at"])
        self._cache[kind] = doc
        return doc

    def _envelope(self, record: dict, freshness: str, error: str | None = None) -> dict:
        meta = next(s for s in SOURCES if s["id"] == record["source"])
        age = (utcnow() - record["fetched_at"]).total_seconds()
        return {"available": True, "freshness": freshness, "fetched_at": record["fetched_at"],
                "age_seconds": round(age), "source": meta["name"], "source_url": meta["url"],
                "license": meta["license"], "attribution": meta["attribution"], "error": error,
                "data": record["data"]}

    @staticmethod
    def _unavailable(source: str, reason: str) -> dict:
        meta = next(s for s in SOURCES if s["id"] == source)
        return {"available": False, "freshness": "unavailable", "fetched_at": None, "age_seconds": None,
                "source": meta["name"], "source_url": meta["url"], "license": meta["license"],
                "attribution": meta["attribution"], "error": reason, "data": None}

    # -- safety-engine view (cache only; never blocks on the network) -------------
    def snapshot(self) -> WeatherSnapshot:
        rec = self._cache.get("forecast")
        if not rec or utcnow() - rec["fetched_at"] > timedelta(hours=3):
            return WeatherSnapshot(available=False)
        cur = rec["data"].get("current", {})
        return WeatherSnapshot(
            available=True, wind_kmh=cur.get("wind_speed_10m"),
            precipitation_probability_pct=rec["data"].get("next_3h_max_precipitation_probability"),
            source="Open-Meteo",
        )

    def refresh(self) -> None:
        for kind in ("forecast", "climate"):
            self.get(kind)

