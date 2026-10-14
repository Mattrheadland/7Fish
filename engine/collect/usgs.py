"""USGS Water Data OGC API (new API only; never waterservices.usgs.gov).

GET https://api.waterdata.usgs.gov/ogcapi/v0/collections/continuous/items
    ?monitoring_location_id=USGS-01638500&parameter_code=00060&time=P3D&f=json&limit=2000
Response: GeoJSON FeatureCollection. Expected feature properties (discovered defensively):
    time, value (often a string), parameter_code, unit_of_measure, monitoring_location_id,
    statistic_id, approval_status, qualifier, time_series_id
Pagination: links[rel=next]. The first feature's property keys are logged under
sources.usgs.shape so a field rename shows up in run_log.json.

One call per parameter code (00060 discharge cfs, 00065 gage height ft, 00010 water temp °C).
Daily-statistics median is not fetched in v1 (spec: "if available, else skip").
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..http import env_key
from ..util import c_to_f, parse_time, to_float

URL = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/continuous/items"
SRC = "usgs"
PARAMS = {"00060": "discharge", "00065": "gage_height", "00010": "water_temp"}
MAX_PAGES = 4

_TIME_KEYS = ("time", "datetime", "phenomenonTime", "date_time")
_VALUE_KEYS = ("value", "result", "observed_value")
_UNIT_KEYS = ("unit_of_measure", "unit", "units", "uom")
_PC_KEYS = ("parameter_code", "parameterCode", "observed_property_id")


def _first(d: dict, keys):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def parse_features(data, wanted_pc: str | None = None) -> tuple[list, str | None]:
    """-> ([(t, value)], unit). Filters by parameter code when the field exists."""
    series, unit = [], None
    for f in (data or {}).get("features") or []:
        pr = (f or {}).get("properties") or {}
        pc = _first(pr, _PC_KEYS)
        if wanted_pc and pc is not None and str(pc) != wanted_pc:
            continue
        stat = pr.get("statistic_id")
        if stat is not None and str(stat) not in ("00011", "00003", ""):  # 00011 = instantaneous
            # keep anyway if it's the only thing present; continuous should all be 00011
            pass
        t = parse_time(_first(pr, _TIME_KEYS))
        v = to_float(_first(pr, _VALUE_KEYS))
        if t is None or v is None:
            continue
        unit = unit or _first(pr, _UNIT_KEYS)
        series.append((t, v))
    series.sort(key=lambda x: x[0])
    return series, unit


def _coords(data):
    try:
        for f in (data or {}).get("features") or []:
            c = ((f or {}).get("geometry") or {}).get("coordinates")
            if isinstance(c, list) and len(c) >= 2:
                return to_float(c[1]), to_float(c[0])
    except Exception:
        pass
    return None, None


def _next_link(data):
    for ln in (data or {}).get("links") or []:
        if isinstance(ln, dict) and ln.get("rel") == "next" and ln.get("href"):
            return ln["href"]
    return None


def fetch(http, site: str) -> dict:
    site = str(site).replace("USGS-", "")
    api_key = env_key("USGS_API_KEY")  # optional; raises the anonymous rate limit
    out = {"site": site, "discharge": [], "gage_height": [], "water_temp": [], "units": {}, "ok": False,
           "lat": None, "lon": None}
    for pc, name in PARAMS.items():
        try:
            params = {"monitoring_location_id": f"USGS-{site}", "parameter_code": pc,
                      "time": "P3D", "f": "json", "limit": 2000}
            key = f"{name}__{site}"
            hdrs = {"X-Api-Key": api_key} if api_key else None
            data = http.get_json(SRC, URL, params=params, key=key, headers=hdrs)
            if data is not None and not (data.get("features") if isinstance(data, dict) else None) \
                    and http.offline_dir is None:
                # Fallback if the duration form of `time` isn't accepted: explicit interval.
                start = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
                p2 = dict(params)
                p2["time"] = f"{start}/.."
                http.log.note(f"usgs {site} {pc}: no features with time=P3D; retried with time={start}/..")
                data = http.get_json(SRC, URL, params=p2, key=key + "__interval", headers=hdrs) or data
            if data is None:
                continue
            series, unit = parse_features(data, pc)
            if out["lat"] is None:
                out["lat"], out["lon"] = _coords(data)
            pages = 1
            nxt = _next_link(data)
            while nxt and pages < MAX_PAGES and http.offline_dir is None:
                more = http.get_json(SRC, nxt, key=f"{key}__p{pages}")
                if more is None:
                    break
                s2, _ = parse_features(more, pc)
                series += s2
                nxt = _next_link(more)
                pages += 1
            series.sort(key=lambda x: x[0])
            if name == "water_temp":
                u = str(unit or "").lower().replace(" ", "")
                if not (u.endswith("f") or "fahrenheit" in u):  # USGS 00010 is °C
                    series = [(t, c_to_f(v)) for t, v in series]
                    unit = "degF"
            out[name] = series
            out["units"][name] = unit
            if series:
                out["ok"] = True
            elif (data or {}).get("features"):
                http.log.error(SRC, f"{site} {pc}: features present but nothing parsed")
        except Exception as e:
            http.log.error(SRC, f"{site} {pc}: {type(e).__name__}: {e}")
    return out
