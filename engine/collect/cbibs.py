"""NOAA CBIBS (Chesapeake Bay Interpretive Buoy System).

GET https://mw.buoybay.noaa.gov/api/v1/json/station/{id}?key=$CBIBS_KEY
  -> {"stations": [{"stationShortName", "stationLongName", "active", "latitude", "longitude",
                    "variable": [{"reportName", "actualName", "units", "measurements":
                                  [{"time": "2026-10-14T10:00:00+00", "value": 15.4, "QA": "GOOD Value"}]}]}]}
`value` may arrive as a number or a string. Skips cleanly when CBIBS_KEY is not set.
"""
from __future__ import annotations

from ..http import env_key
from ..util import c_to_f, parse_time, to_float

BASE = "https://mw.buoybay.noaa.gov/api/v1/json/station"
SRC = "cbibs"
WANT = {
    "sea_water_temperature": "water_temp",
    "simple_turbidity": "turbidity",
    "mass_concentration_of_oxygen_in_sea_water": "do",
    "sea_surface_wave_significant_height": "wave_height",
}


def fetch(http, station: str) -> dict:
    out = {"station": station, "active": None, "values": {}, "ok": False, "skipped": None}
    key = env_key("CBIBS_KEY")
    if not key and http.offline_dir is None:
        out["skipped"] = "CBIBS_KEY not set"
        http.log.skipped(SRC, "CBIBS_KEY not set")
        return out
    try:
        d = http.get_json(SRC, f"{BASE}/{station}", params={"key": key or ""}, key=f"station__{station}")
        stations = (d or {}).get("stations") or []
        st = stations[0] if stations and isinstance(stations[0], dict) else {}
        out["active"] = st.get("active")
        for var in st.get("variable") or []:
            name = WANT.get(str(var.get("actualName")))
            if not name:
                continue
            meas = [m for m in var.get("measurements") or [] if isinstance(m, dict)]
            if not meas:
                continue
            m = max(meas, key=lambda m: parse_time(m.get("time")) or parse_time("1970-01-01T00:00+00:00"))
            v = to_float(m.get("value"))
            t = parse_time(m.get("time"))
            unit = var.get("units")
            if name == "water_temp" and v is not None and "f" not in str(unit).lower():
                v, unit = c_to_f(v), "degF"
            qa = str(m.get("QA", ""))
            if v is not None and "bad" not in qa.lower():
                out["values"][name] = {"v": v, "unit": unit, "at": t, "qa": qa}
        out["ok"] = bool(out["values"])
    except Exception as e:
        http.log.error(SRC, f"{station}: {type(e).__name__}: {e}")
    return out
