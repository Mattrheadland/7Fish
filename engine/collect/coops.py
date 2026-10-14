"""NOAA CO-OPS datagetter.

https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?product=...&station=...
  predictions (interval=hilo): {"predictions": [{"t": "2026-10-14 03:12", "v": "2.345", "type": "H"}]}
  water_temperature / water_level / air_pressure: {"metadata": {"id","name","lat","lon"}, "data": [{"t","v","f"}]}
  wind: {"metadata": {...}, "data": [{"t","s","d","dr","g","f"}]}
  error: {"error": {"message": "..."}}
time_zone=lst_ldt -> local station time (ET for MD stations).
"""
from __future__ import annotations

from datetime import timedelta

from ..util import ET, parse_time, to_float

URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
SRC = "coops"
COMMON = {"units": "english", "time_zone": "lst_ldt", "format": "json", "application": "7Fish"}


def _data(http, station, product, key, extra):
    params = dict(COMMON, station=station, product=product, **extra)
    d = http.get_json(SRC, URL, params=params, key=f"{key}__{station}", shape_label=product)
    if isinstance(d, dict) and d.get("error"):
        msg = (d.get("error") or {}).get("message") if isinstance(d.get("error"), dict) else str(d.get("error"))
        http.log.error(SRC, f"{station} {product}: {msg}")
        return None
    return d


def fetch(http, station: str, now, has=None) -> dict:
    has = set(has or [])
    want = lambda *keys: (not has) or bool(has & set(keys))
    out = {"station": station, "hilo": [], "water_temp": [], "water_level": [], "air_pressure": [],
           "wind": [], "meta": {}, "ok": False}
    begin = (now.astimezone(ET) - timedelta(days=1)).strftime("%Y%m%d")
    end = (now.astimezone(ET) + timedelta(days=4)).strftime("%Y%m%d")
    try:
        d = _data(http, station, "predictions", "predictions",
                  {"interval": "hilo", "datum": "MLLW", "begin_date": begin, "end_date": end}) if want("tide_predictions", "water_level") else None
        for p in (d or {}).get("predictions") or []:
            t = parse_time(p.get("t"), assume_tz=ET)
            if t is None:
                continue
            typ = str(p.get("type", "")).upper()[:1] or None
            out["hilo"].append({"t": t, "v": to_float(p.get("v")), "type": typ})
        out["hilo"].sort(key=lambda x: x["t"])
    except Exception as e:
        http.log.error(SRC, f"{station} predictions: {type(e).__name__}: {e}")
    for product in ("water_temperature", "water_level", "air_pressure"):
        if not want({"water_temperature": "water_temp", "water_level": "water_level", "air_pressure": "barometric_pressure"}[product]):
            continue
        try:
            extra = {"date": "recent"}
            if product == "water_level":
                extra["datum"] = "MLLW"
            d = _data(http, station, product, product, extra)
            if d and isinstance(d.get("metadata"), dict):
                out["meta"] = d["metadata"]
            ser = []
            for row in (d or {}).get("data") or []:
                t = parse_time(row.get("t"), assume_tz=ET)
                v = to_float(row.get("v"))
                if t is not None and v is not None:
                    ser.append((t, v))
            name = "water_temp" if product == "water_temperature" else product
            out[name] = ser
        except Exception as e:
            http.log.error(SRC, f"{station} {product}: {type(e).__name__}: {e}")
    try:
        d = _data(http, station, "wind", "wind", {"date": "recent"}) if want("wind") else None
        for row in (d or {}).get("data") or []:
            t = parse_time(row.get("t"), assume_tz=ET)
            if t is None:
                continue
            out["wind"].append({"t": t, "speed_kt": to_float(row.get("s")), "dir_deg": to_float(row.get("d")),
                                "gust_kt": to_float(row.get("g"))})
    except Exception as e:
        http.log.error(SRC, f"{station} wind: {type(e).__name__}: {e}")
    out["ok"] = bool(out["hilo"] or out["water_temp"] or out["water_level"] or out["air_pressure"] or out["wind"])
    return out
