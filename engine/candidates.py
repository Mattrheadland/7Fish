"""Candidate rows (spot × species × window), word tiers and confidence.

Tier = season word for region/month, then one step down for each minus listed in SPEC,
one step up at most once (water temp peak AND two or more plus prefs), floored at Poor.
Numbers appear only as internal sort keys (TIER_RANK, CONF_RANK); output carries words.
"""
from __future__ import annotations

from datetime import datetime

from .gates import all_pass, species_window_gates
from .knowledge import norm_status
from .util import drive_minutes

TIERS = ["Poor", "Fair", "Good", "Prime"]
TIER_RANK = {t: i for i, t in enumerate(TIERS)}
CONFS = ["low", "medium", "high"]
CONF_RANK = {c: i for i, c in enumerate(CONFS)}
SEASON_TO_TIER = {"prime": "Prime", "good": "Good", "fair": "Fair", "poor": "Poor"}
TIDAL_TYPES = {"tidal-river", "bay", "pier", "inlet"}


def temp_band(species: dict, wt_f):
    """Return band name for a water temp in °F, or None. Bands: min inclusive, max exclusive."""
    if wt_f is None:
        return None
    for b in species.get("temp_bands_f") or []:
        if not isinstance(b, dict):
            continue
        lo, hi = b.get("min"), b.get("max")
        if (lo is None or wt_f >= lo) and (hi is None or wt_f < hi):
            return str(b.get("band", "")).lower() or None
    return None


def _pref(species, group, key):
    p = (species.get("prefs") or {}).get(group) or {}
    if not isinstance(p, dict) or key is None:
        return None
    v = p.get(key)
    return str(v).lower() if v is not None else None


def step(tier: str, n: int) -> str:
    return TIERS[max(0, min(len(TIERS) - 1, TIER_RANK[tier] + n))]


def tier_for(species: dict, season_word: str, cond: dict, feats: dict, water_type: str) -> tuple[str, list, dict]:
    """Return (tier, reasons, info). Pure; unit-tested."""
    reasons = []
    base = SEASON_TO_TIER.get(season_word or "", "Poor")
    reasons.append({"text": f"season '{season_word}' for the region this month", "label": "reasoning", "src": "species file"})
    downs, plus = 0, 0
    # water temp
    wt = (feats.get("water_temp") or {})
    band = temp_band(species, wt.get("v")) if wt.get("label") == "measured" else None
    if band in ("slow", "inactive", "stressed"):
        downs += 1
        reasons.append({"text": f"water {wt['v']:.0f}°F is the '{band}' band (−1)", "label": "measured", "src": wt.get("src")})
    elif band:
        reasons.append({"text": f"water {wt['v']:.0f}°F is the '{band}' band", "label": "measured", "src": wt.get("src")})
    elif wt.get("label") != "measured":
        reasons.append({"text": "water temp not found within 25 mi; no temp adjustment", "label": "not_found"})
    # flow trend
    fl = cond.get("flow") or {}
    ftrend = (feats.get("flow") or {}).get("trend_72h")
    fp = _pref(species, "flow", ftrend) if ftrend in ("rising", "falling") else None
    if fp == "minus":
        downs += 1
        reasons.append({"text": f"flow {ftrend} (species pref minus, −1)", "label": "measured", "src": (feats.get('flow') or {}).get('current', {}).get('src')})
    elif fp == "plus":
        plus += 1
        reasons.append({"text": f"flow {ftrend} (species pref plus)", "label": "measured", "src": (feats.get('flow') or {}).get('current', {}).get('src')})
    # clarity
    clar = (feats.get("clarity_proxy") or {})
    if clar.get("v") == "likely_muddy" and _pref(species, "flow", "high_muddy") == "minus":
        downs += 1
        reasons.append({"text": f"likely muddy water ({clar.get('basis')}) (−1)", "label": clar.get("label", "reasoning")})
    # light
    light = cond.get("light") or {}
    lp = _pref(species, "light", light.get("type"))
    if light.get("overcast") and _pref(species, "light", "overcast") == "plus":
        if lp == "minus":
            lp = "neutral"
        plus += 1
        reasons.append({"text": "overcast window (species pref plus)", "label": "modeled", "src": "Open-Meteo cloud"})
    if lp == "minus":
        downs += 1
        reasons.append({"text": f"{light.get('type')} light (species pref minus, −1)", "label": "reasoning"})
    elif lp == "plus":
        plus += 1
        reasons.append({"text": f"{light.get('type')} window (species pref plus)", "label": "reasoning"})
    # front
    fr = cond.get("front")
    frp = _pref(species, "front", fr)
    if frp == "minus":
        downs += 1
        reasons.append({"text": f"pressure {fr.replace('_', ' ')} (species pref minus, −1)", "label": "forecast", "src": "Open-Meteo"})
    elif frp == "plus":
        plus += 1
        reasons.append({"text": f"pressure {fr.replace('_', ' ')} (species pref plus)", "label": "forecast", "src": "Open-Meteo"})
    # tide
    if water_type in TIDAL_TYPES and cond.get("tide"):
        ts = (cond.get("tide") or {}).get("dominant")
        tp = _pref(species, "tide", ts)
        if tp == "minus":
            downs += 1
            reasons.append({"text": f"mostly {ts} tide in window (−1)", "label": "forecast", "src": "CO-OPS predictions"})
        elif tp == "plus":
            plus += 1
            reasons.append({"text": f"{ts} tide in window (species pref plus)", "label": "forecast", "src": "CO-OPS predictions"})
    tier = step(base, -downs)
    up = band == "peak" and plus >= 2
    if up:
        tier = step(tier, +1)
        reasons.append({"text": "peak water temp plus two favorable conditions (+1)", "label": "reasoning"})
    return tier, reasons, {"band": band, "downs": downs, "plus": plus, "up": up, "base": base}


def confidence_for(feats: dict, water_type: str, dnr_fresh_mention: bool) -> tuple[str, str]:
    wt_ok = (feats.get("water_temp") or {}).get("label") == "measured"
    fl = feats.get("flow") or {}
    flow_ok = (fl.get("current") or {}).get("label") == "measured" or (fl.get("stage") or {}).get("label") == "measured"
    tide_ok = (feats.get("tide") or {}).get("label") == "forecast" and water_type in TIDAL_TYPES
    water_ok = flow_ok or tide_ok
    # high needs measured water temp + flow/tide + fresh DNR mention (SPEC). Start from
    # flow/tide + DNR (both -> high, one -> medium, none -> low), then a missing water temp
    # drops one level.
    lvl = int(water_ok) + int(dnr_fresh_mention)
    notes = []
    notes.append("flow/tide data in hand" if water_ok else "no flow or tide data")
    notes.append("DNR report under 30 days mentions it" if dnr_fresh_mention else "no fresh DNR mention")
    if not wt_ok:
        lvl = max(0, lvl - 1)
        notes.append("water temp not measured nearby")
    else:
        notes.append("water temp measured")
    return CONFS[lvl], "; ".join(notes)


def luca_ok(spot, species, w) -> bool:
    if not spot.get("luca_ok") or not species.get("kid_friendly"):
        return False
    if w["kind"] == "night":
        return False
    end = (w.get("clip") or {}).get("end", w["end"])
    return end <= w["sunset"]


def trips_for(drive_min, trip_cfg) -> list[str]:
    out = []
    for name in ("quick", "half", "full"):
        lim = (trip_cfg.get(name) or {}).get("max_drive_min")
        if isinstance(lim, (int, float)) and drive_min <= lim:
            out.append(name)
    return out


def dnr_fresh(dnr: dict, species_key: str, now: datetime, fresh_days=30) -> bool:
    if not dnr or not dnr.get("date") or species_key not in (dnr.get("by_species") or {}):
        return False
    try:
        d = datetime.fromisoformat(dnr["date"]).date()
    except Exception:
        return False
    return (now.date() - d).days <= fresh_days


def build(kn, spot_results: dict, dnr: dict, now: datetime) -> list[dict]:
    origin = kn.profile.get("origin") or {}
    olat, olon = origin.get("lat", 39.4143), origin.get("lon", -77.4105)
    trip_cfg = kn.profile.get("trip_types") or {}
    fresh_days = kn.gates.get("dnr", {}).get("fresh_days", 30)
    rows = []
    for sid, res in spot_results.items():
        spot = kn.spots[sid]
        region = spot.get("region")
        wtype = str(spot.get("water_type") or "river")
        dmin = drive_minutes(spot["lat"], spot["lon"], olat, olon)
        trips = trips_for(dmin, trip_cfg)
        feats = res["features"]
        sp_map = spot.get("species") or {}
        if isinstance(sp_map, list):  # tolerate a list of keys or {key: ...} items
            sp_map = {(x if isinstance(x, str) else (x.get("key") or x.get("id") or "")): (x if isinstance(x, dict) else {})
                      for x in sp_map if isinstance(x, (str, dict))}
        for skey, sp_entry in sp_map.items():
            species = kn.species.get(skey)
            if species is None:
                continue
            if isinstance(sp_entry, dict) and norm_status(sp_entry.get("presence")) == "ruled out":
                continue
            fresh = dnr_fresh(dnr, skey, now, fresh_days)
            conf, conf_note = confidence_for(feats, wtype, fresh)
            for w in res["windows"]:
                if not all_pass(w["gates"]):
                    continue
                sg = species_window_gates(kn, skey, region, w)
                w.setdefault("species_gates", {})[skey] = sg
                if not all_pass(sg):
                    continue
                month = datetime.fromisoformat(w["date"]).month
                word = kn.season_word(skey, region, month)
                tier, reasons, info = tier_for(species, word, w["conditions"], feats, wtype)
                if fresh:
                    reasons.append({"text": f"DNR report {dnr['date']} mentions this species", "label": "report", "src": dnr.get("link")})
                methods = [m.get("id") for m in species.get("methods") or [] if isinstance(m, dict) and m.get("id")]
                rows.append({
                    "spot": sid, "species": skey, "window": w["id"], "tier": tier, "confidence": conf,
                    "confidence_note": conf_note, "drive_min": dmin, "trips": trips,
                    "luca_ok": luca_ok(spot, species, w), "reasons": reasons, "methods": methods,
                    "_w": w, "_info": info,
                })
    rows.sort(key=sort_key)
    return rows


def sort_key(r):
    """Internal ordering only: tier, then confidence, then shorter drive, then earlier window."""
    return (-TIER_RANK[r["tier"]], -CONF_RANK[r["confidence"]], r["drive_min"], r["_w"]["start"])
