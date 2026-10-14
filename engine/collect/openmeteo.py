"""Open-Meteo forecast API (past 3 days + 4 forecast days).

Shape: {"latitude", "longitude", "timezone", "hourly_units": {...},
        "hourly": {"time": ["2026-10-14T00:00", ...], "pressure_msl": [...], ...}}
Times are local to `timezone=America/New_York`.

Open-Meteo's temperature_2m is AIR temperature. No surface/soil temperature is requested
or ever used as water temperature.
"""
from __future__ import annotations

from ..util import ET, parse_time, to_float

URL = "https://api.open-meteo.com/v1/forecast"
SRC = "openmeteo"
VARS = ["pressure_msl", "cloud_cover", "wind_speed_10m", "wind_gusts_10m", "wind_direction_10m",
        "precipitation", "temperature_2m"]


def fetch(http, lat: float, lon: float) -> dict:
    params = {
        "latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}",
        "hourly": ",".join(VARS), "past_days": 3, "forecast_days": 6,
        "timezone": "America/New_York", "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph", "precipitation_unit": "inch",
    }
    out = {"series": {v: [] for v in VARS}, "ok": False}
    try:
        data = http.get_json(SRC, URL, params=params, key=f"forecast__{lat:.4f},{lon:.4f}")
        hourly = (data or {}).get("hourly") or {}
        times = [parse_time(t, assume_tz=ET) for t in hourly.get("time") or []]
        for v in VARS:
            arr = hourly.get(v) or []
            out["series"][v] = [(t, to_float(x)) for t, x in zip(times, arr) if t is not None]
        out["ok"] = bool(times)
        if data is not None and not times:
            http.log.error(SRC, f"no hourly.time in response; keys={list((data or {}).keys())[:10]}")
    except Exception as e:
        http.log.error(SRC, f"{type(e).__name__}: {e}")
    return out
