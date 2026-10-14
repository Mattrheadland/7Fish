"""NOAA National Water Prediction Service API.

GET https://api.water.noaa.gov/nwps/v1/gauges/{lid}
  -> {"lid", "name", "latitude", "longitude",
      "flood": {"stageUnits": "ft", "flowUnits": "kcfs",
                "categories": {"action": {"stage": 15, "flow": -9999}, "minor": {...}, "moderate": {...}, "major": {...}}},
      "status": {"observed": {"primary", "primaryUnit", "secondary", "secondaryUnit", "floodCategory", "validTime"},
                 "forecast": {...same...}}}
GET https://api.water.noaa.gov/nwps/v1/gauges/{lid}/stageflow
  -> {"observed": {"primaryUnits": "ft", "secondaryUnits": "kcfs", "data": [{"validTime", "primary", "secondary"}]},
      "forecast": {...same...}}
-999/-9999 mean missing. Flow in kcfs is converted to cfs.
"""
from __future__ import annotations

from ..util import parse_time, to_float

BASE = "https://api.water.noaa.gov/nwps/v1/gauges"
SRC = "nwps"
CATS = ["action", "minor", "moderate", "major"]


def _flow_to_cfs(v, unit):
    if v is None:
        return None
    u = str(unit or "").lower()
    if "kcfs" in u:
        return v * 1000
    return v


def _series(block):
    block = block or {}
    pu = block.get("primaryUnits") or block.get("primaryUnit")
    su = block.get("secondaryUnits") or block.get("secondaryUnit")
    stage, flow = [], []
    for d in block.get("data") or []:
        if not isinstance(d, dict):
            continue
        t = parse_time(d.get("validTime"))
        if t is None:
            continue
        p = to_float(d.get("primary"))
        s = to_float(d.get("secondary"))
        if p is not None:
            stage.append((t, p))
        if s is not None:
            flow.append((t, _flow_to_cfs(s, su)))
    return {"stage": stage, "flow": flow, "stage_unit": pu, "flow_unit": "cfs" if su else None}


def category_for(stage, cats: dict) -> str:
    """Highest category whose stage threshold the value meets; 'none' below action."""
    if stage is None:
        return "unknown"
    found = "none"
    for c in CATS:
        th = (cats.get(c) or {}).get("stage")
        if th is not None and stage >= th:
            found = c
    return found


def fetch(http, lid: str) -> dict:
    out = {"lid": lid, "categories": {}, "observed": {}, "forecast": {}, "status": {}, "ok": False}
    try:
        g = http.get_json(SRC, f"{BASE}/{lid}", key=f"gauge__{lid}", shape_label="gauge")
        if g is not None:
            fl = g.get("flood") or {}
            cats = fl.get("categories") or {}
            fu = fl.get("flowUnits")
            for c in CATS:
                cd = cats.get(c) or {}
                out["categories"][c] = {"stage": to_float(cd.get("stage")),
                                        "flow": _flow_to_cfs(to_float(cd.get("flow")), fu)}
            st = g.get("status") or {}
            for k in ("observed", "forecast"):
                s = st.get(k) or {}
                out["status"][k] = {"stage": to_float(s.get("primary")), "flow": _flow_to_cfs(to_float(s.get("secondary")), s.get("secondaryUnit")),
                                    "category": s.get("floodCategory"), "at": parse_time(s.get("validTime"))}
            out["ok"] = True
    except Exception as e:
        http.log.error(SRC, f"gauge {lid}: {type(e).__name__}: {e}")
    try:
        sf = http.get_json(SRC, f"{BASE}/{lid}/stageflow", key=f"stageflow__{lid}", shape_label="stageflow")
        if sf is not None:
            out["observed"] = _series(sf.get("observed"))
            out["forecast"] = _series(sf.get("forecast"))
            out["ok"] = True
    except Exception as e:
        http.log.error(SRC, f"stageflow {lid}: {type(e).__name__}: {e}")
    return out
