"""NWS api.weather.gov: hourly forecast, gridpoint gusts, active alerts.

Shapes (public docs):
  /points/{lat},{lon} -> {"properties": {"forecastHourly": url, "forecastGridData": url, ...}}
  forecastHourly      -> {"properties": {"periods": [{"startTime", "endTime", "temperature",
                          "temperatureUnit", "windSpeed": "5 to 10 mph", "windDirection": "NW",
                          "shortForecast", "probabilityOfPrecipitation": {"value"}}]}}
  forecastGridData    -> {"properties": {"windGust": {"uom": "wmoUnit:km_h-1",
                          "values": [{"validTime": "2026-10-14T10:00:00+00:00/PT2H", "value": 24.1}]}}}
  /alerts/active?point=lat,lon -> {"features": [{"properties": {"event", "onset", "effective",
                          "ends", "expires", "headline", "severity"}}]}
"""
from __future__ import annotations

import re
from datetime import timedelta

from ..util import cardinal_to_deg, kmh_to_mph, parse_iso_duration_h, parse_time, to_float

BASE = "https://api.weather.gov"
SRC = "nws"


def _key(lat, lon):
    return f"{lat:.4f},{lon:.4f}"


def _wind_mph(s):
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    if isinstance(s, dict):  # newer format {"unitCode": "wmoUnit:km_h-1", "value": 16}
        v = to_float(s.get("value"))
        if v is not None and "km_h" in str(s.get("unitCode", "")):
            return kmh_to_mph(v)
        return v
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(s))]
    return max(nums) if nums else None


def _gust_from_text(s):
    m = re.search(r"gusts?\s*(?:as high as|to|up to)?\s*(\d+)", str(s or ""), re.I)
    return float(m.group(1)) if m else None


def fetch(http, lat: float, lon: float) -> dict:
    out = {"hourly": [], "alerts": [], "office": None, "ok_hourly": False, "ok_alerts": False}
    k = _key(lat, lon)
    try:
        pts = http.get_json(SRC, f"{BASE}/points/{lat:.4f},{lon:.4f}", key=f"points__{k}", shape_label="points")
        props = (pts or {}).get("properties") or {}
        out["office"] = props.get("gridId")
        hourly_url = props.get("forecastHourly")
        grid_url = props.get("forecastGridData")
        gusts = []
        if grid_url or http.offline_dir is not None:
            grid = http.get_json(SRC, grid_url or "offline", key=f"grid__{k}", shape_label="grid")
            gusts = _parse_gusts(grid)
        if hourly_url or http.offline_dir is not None:
            fh = http.get_json(SRC, hourly_url or "offline", key=f"hourly__{k}", shape_label="hourly")
            out["hourly"] = _parse_hourly(fh, gusts)
            out["ok_hourly"] = bool(out["hourly"])
        elif pts is not None:
            http.log.error(SRC, f"points {k}: no forecastHourly in properties")
    except Exception as e:
        http.log.error(SRC, f"hourly {k}: {type(e).__name__}: {e}")
    try:
        al = http.get_json(SRC, f"{BASE}/alerts/active", params={"point": f"{lat:.4f},{lon:.4f}"},
                           key=f"alerts__{k}", shape_label="alerts")
        if al is not None:
            out["alerts"] = _parse_alerts(al)
            out["ok_alerts"] = True
    except Exception as e:
        http.log.error(SRC, f"alerts {k}: {type(e).__name__}: {e}")
    return out


def _parse_gusts(grid) -> list:
    """-> list of (start, end, mph)"""
    res = []
    wg = ((grid or {}).get("properties") or {}).get("windGust") or {}
    uom = str(wg.get("uom", "km_h"))
    for item in wg.get("values") or []:
        if not isinstance(item, dict):
            continue
        vt = item.get("validTime") or ""
        start = parse_time(vt)
        v = to_float(item.get("value"))
        if start is None or v is None:
            continue
        hours = parse_iso_duration_h(vt.split("/", 1)[1]) if "/" in vt else 1.0
        mph = kmh_to_mph(v) if "km_h" in uom else v
        res.append((start, start + timedelta(hours=hours), mph))
    return res


def _parse_hourly(fh, gusts) -> list:
    periods = ((fh or {}).get("properties") or {}).get("periods") or []
    res = []
    for p in periods:
        if not isinstance(p, dict):
            continue
        t = parse_time(p.get("startTime"))
        if t is None:
            continue
        temp = to_float(p.get("temperature"))
        if isinstance(p.get("temperature"), dict):
            temp = to_float(p["temperature"].get("value"))
        if temp is not None and str(p.get("temperatureUnit", "F")).upper().startswith("C"):
            temp = temp * 9 / 5 + 32
        pop = p.get("probabilityOfPrecipitation")
        pop = to_float(pop.get("value")) if isinstance(pop, dict) else to_float(pop)
        gust = None
        for gs, ge, mph in gusts:
            if gs <= t < ge:
                gust = mph
                break
        if gust is None:
            gust = _wind_mph(p.get("windGust")) if p.get("windGust") else _gust_from_text(p.get("detailedForecast"))
        res.append({
            "t": t,
            "temp_f": temp,
            "wind_mph": _wind_mph(p.get("windSpeed")),
            "wind_dir_deg": cardinal_to_deg(p.get("windDirection")),
            "gust_mph": gust,
            "pop": pop,
            "short": p.get("shortForecast") or "",
        })
    res.sort(key=lambda r: r["t"])
    return res


def _parse_alerts(al) -> list:
    res = []
    for f in (al or {}).get("features") or []:
        pr = (f or {}).get("properties") or {}
        ev = pr.get("event")
        if not ev:
            continue
        res.append({
            "event": ev,
            "start": parse_time(pr.get("onset") or pr.get("effective")),
            "end": parse_time(pr.get("ends") or pr.get("expires")),
            "headline": (pr.get("headline") or "")[:200],
            "severity": pr.get("severity"),
        })
    return res
