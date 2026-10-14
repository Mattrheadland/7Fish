"""Hard stops. Each gate returns {"name", "pass", "reason"}. A missing input never passes
silently as 'verified': it passes with a reason that says what wasn't checked, except
where the spec says unknown means fail (after-dark windows with hours not found)."""
from __future__ import annotations

from datetime import datetime, time

from .features import cat_at_least
from .knowledge import is_ruled_out
from .util import ET


def g(name, ok, reason) -> dict:
    return {"name": name, "pass": bool(ok), "reason": reason}


# ---------------------------------------------------------------- spot-window gates
def alert_gate(alerts, w, water_type, cfg, checked=True) -> dict:
    acfg = cfg.get("alerts", {})
    by_type = set(a.lower() for a in (acfg.get("water_types") or {}).get(water_type or "", []) or [])
    listed = set(a.lower() for a in acfg.get("all_spots") or []) | by_type
    never = set(a.lower() for a in acfg.get("not_gates") or []) - by_type  # water-type listing wins
    if not checked:
        return g("alerts", True, "NWS alerts not retrieved; not checked")
    for a in alerts or []:
        ev = str(a.get("event", "")).lower()
        if ev in never or ev not in listed:
            continue
        s = a.get("start") or w["start"]
        e = a.get("end") or w["end"]
        if s < w["end"] and e > w["start"]:
            return g("alerts", False, f"{a.get('event')} in effect during window")
    return g("alerts", True, "no gating NWS alert in window")


def thunder_gate(shorts, cfg, checked=True) -> dict:
    if not checked:
        return g("thunder", True, "NWS hourly forecast not retrieved; thunder not checked")
    kws = [k.lower() for k in cfg.get("thunder_keywords") or ["thunder"]]
    for s in shorts or []:
        if any(k in str(s).lower() for k in kws):
            return g("thunder", False, f"forecast says '{s}'")
    return g("thunder", True, "no thunder in hourly forecast")


def gust_gate(max_gust, limit) -> dict:
    if max_gust is None:
        return g("wind", True, "gust forecast not found; not checked")
    if max_gust > limit:
        return g("wind", False, f"gusts to {max_gust:.0f} mph over the {limit:.0f} mph limit")
    return g("wind", True, f"max gust {max_gust:.0f} mph within {limit:.0f} mph limit")


def flow_gate(wflow: dict | None, ceiling_source: str | None, cfg) -> dict:
    if not wflow:
        return g("flow", True, "n/a for this water")
    vs = wflow.get("vs_ceiling")
    cat = wflow.get("nwps_category") or "unknown"
    if vs == "over":
        return g("flow", False, f"flow {wflow.get('v')} {wflow.get('unit')} over the fishable ceiling ({wflow.get('label')})")
    block = (cfg.get("flow", {}).get("block_categories") or ["action"])
    floor = block[0] if block else "action"
    if str(ceiling_source or "").lower() in ("ask_matt", "not found", "") and cat_at_least(cat, floor):
        return g("flow", False, f"NWPS forecast category '{cat}' at or above {floor}; no ceiling set (ask Matt)")
    if cat_at_least(cat, "minor"):
        return g("flow", False, f"NWPS flood category '{cat}'")
    if vs == "unknown":
        return g("flow", True, "flow ceiling not set or flow not found; not checked")
    return g("flow", True, f"flow {vs} ceiling")


def _clock(spec, w, which):
    """Resolve an open/close spec to an aware datetime on the window date, or a keyword."""
    if spec is None:
        return "not found"
    s = str(spec).strip().lower()
    if s in ("not found", "not_found", "unknown", ""):
        return "not found"
    if s in ("24h", "24 h", "always"):
        return "24h"
    if s == "sunrise":
        return w["sunrise"]
    if s == "sunset":
        return w["sunset"]
    try:
        hh, mm = s.split(":")[:2]
        d = datetime.fromisoformat(w["date"]).date()
        return datetime.combine(d, time(int(hh), int(mm)), tzinfo=ET)
    except Exception:
        return "not found"


def hours_gate(spot, w) -> dict:
    acc = spot.get("access") or {}
    hrs = acc.get("hours") or {}
    if not isinstance(hrs, dict):
        hrs = {}
    after_dark = str(acc.get("after_dark") or "not_verified").lower()
    op, cl = _clock(hrs.get("open"), w, "open"), _clock(hrs.get("close"), w, "close")
    if w["kind"] == "night" and after_dark != "allowed":
        return g("hours", False, "after-dark access not verified")
    if op == "not found" or cl == "not found":
        if w["kind"] == "night":
            return g("hours", False, "posted hours not found; after-dark windows excluded")
        return g("hours", True, "posted hours not found; daylight windows only")
    if op == "24h" or cl == "24h":
        return g("hours", True, "open 24 hours")
    if w["end"] <= op or w["start"] >= cl:
        return g("hours", False, f"window outside posted hours ({hrs.get('open')}–{hrs.get('close')})")
    if w["start"] < op or w["end"] > cl:
        w["clip"] = {"start": max(w["start"], op), "end": min(w["end"], cl)}
        return g("hours", True, f"window clipped to posted hours ({hrs.get('open')}–{hrs.get('close')})")
    return g("hours", True, f"inside posted hours ({hrs.get('open')}–{hrs.get('close')})")


def status_gate(spot) -> dict:
    if is_ruled_out(spot.get("status")):
        return g("status", False, "spot ruled out")
    return g("status", True, "spot active")


def spot_window_gates(spot, w, alerts, alerts_checked, cfg) -> list[dict]:
    cond = w.get("conditions") or {}
    limit = spot.get("wind_gust_limit_mph")
    if not isinstance(limit, (int, float)):
        limit = cfg.get("wind", {}).get("default_gust_limit_mph", 30)
    wcheck = bool(cond.get("weather_checked"))
    return [
        alert_gate(alerts, w, spot.get("water_type"), cfg, alerts_checked),
        thunder_gate(cond.get("short"), cfg, wcheck),
        gust_gate((cond.get("wind") or {}).get("max_gust_mph"), float(limit)),
        flow_gate(cond.get("flow"), (spot.get("flow_ceiling") or {}).get("source"), cfg),
        hours_gate(spot, w),
        status_gate(spot),
    ]


# ---------------------------------------------------------------- species-window gates
def species_window_gates(kn, species_key, region, w) -> list[dict]:
    d = datetime.fromisoformat(w["date"]).date()
    closed, note, src = kn.targeting_closed(species_key, region, d)
    out = [g("season_closed", not closed,
             f"targeting closed: {note}" if closed else ("no targeting closure found in regs.yaml" if kn.regs else "regs.yaml not loaded; closures not checked"))]
    word = kn.season_word(species_key, region, d.month)
    if word in ("absent", "closed"):
        out.append(g("presence_month", False, f"season calendar says '{word}' for {region} in month {d.month}"))
    elif word is None:
        out.append(g("presence_month", False, f"no season entry for {region} in month {d.month}"))
    else:
        out.append(g("presence_month", True, f"season '{word}' for {region}"))
    return out


def all_pass(gs) -> bool:
    return all(x["pass"] for x in gs)
