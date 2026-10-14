"""Compact payload for the 7 Fish Cast screen: data/app.json.

The app stores this as one database document, so it has to stay small (target < 300 KB).
It carries only what the Cast screen and the in-app Forecaster need: conditions per spot and
window, passing candidates, baseline cards, and the slices of knowledge a card cites.
"""
from __future__ import annotations

import json
from pathlib import Path

PER_DAY = 45  # keep the best candidates for every forecast day, so weekend casts have rows


def _v(x):
    """Trim a value object to its essentials."""
    if not isinstance(x, dict):
        return x
    keep = ("v", "unit", "label", "src", "dist_mi", "at", "note")
    out = {k: x[k] for k in keep if x.get(k) is not None}
    if isinstance(x.get("trend_72h"), dict):
        out["trend"] = x["trend_72h"].get("class")
    return out


def _txt(x):
    if isinstance(x, dict):
        return x.get("text") or x.get("value")
    return x


def _spot_kn(spot: dict) -> dict:
    acc = spot.get("access") or {}
    hours = acc.get("hours") or {}
    jur = spot.get("jurisdiction") or {}
    sp = spot.get("species") or {}
    pqa = {}
    if isinstance(sp, dict):
        for k, e in sp.items():
            if isinstance(e, dict):
                ev = []
                for item in (e.get("evidence") or [])[:2]:
                    if isinstance(item, dict):
                        ev.append({k2: item.get(k2) for k2 in ("text", "date", "tag") if item.get(k2)})
                pqa[k] = {"presence": e.get("presence"), "quality": e.get("quality"), "evidence": ev}
    return {
        "access_status": acc.get("status"),
        "parking": _txt(acc.get("parking")), "walk": _txt(acc.get("walk")), "stand": _txt(acc.get("stand")),
        "casting": _txt(acc.get("casting")), "landing": _txt(acc.get("landing")),
        "hours": {"text": hours.get("text"), "open": hours.get("open"), "close": hours.get("close")} if isinstance(hours, dict) else {"text": hours},
        "after_dark": acc.get("after_dark"),
        "license": jur.get("license"), "flags": jur.get("flags") or [],
        "crowding": spot.get("crowding"), "hazards": (spot.get("hazards") or [])[:4],
        "matt_notes": spot.get("matt_notes") or [], "luca_ok": bool(spot.get("luca_ok")),
        "species": pqa,
    }


def _species_kn(sp: dict) -> dict:
    methods = []
    for m in sp.get("methods") or []:
        if isinstance(m, dict):
            methods.append({k: m.get(k) for k in ("id", "when", "rig_line", "switch_to", "switch_trigger", "gear_note") if m.get(k)})
    adv = sp.get("advisory") or {}
    return {"name": sp.get("name"), "kid_friendly": bool(sp.get("kid_friendly")), "methods": methods,
            "advisory": adv.get("url") if isinstance(adv, dict) else None}


def _regs(regs: dict) -> dict:
    out = {}
    for skey, entries in ((regs or {}).get("species") or {}).items():
        rows = []
        for e in entries or []:
            if not isinstance(e, dict):
                continue
            rows.append({k: e.get(k) for k in ("area", "regions", "harvest", "targeting_closed", "src", "tag", "warning") if e.get(k) not in (None, [], "")})
        out[skey] = rows
    return out


def _window(w: dict) -> dict:
    c = w.get("conditions") or {}
    fails = [g.get("reason") for g in w.get("gates") or [] if not g.get("pass")]
    return {"id": w.get("id"), "kind": w.get("kind"), "start": (w.get("clip") or {}).get("start") or w.get("start"),
            "end": (w.get("clip") or {}).get("end") or w.get("end"), "cond": c, "fails": fails}


def build(latest: dict, kn) -> dict:
    spots = {}
    for sid, s in (latest.get("spots") or {}).items():
        f = s.get("features") or {}
        fl = f.get("flow") or {}
        flow = None
        if fl.get("applies"):
            flow = {"now": _v(fl.get("current")), "stage": _v(fl.get("stage")), "trend": fl.get("trend_72h"),
                    "change_48h": fl.get("change_48h"), "vs_ceiling": fl.get("vs_ceiling"),
                    "ceiling": fl.get("ceiling"), "nwps": {k: fl.get(k) for k in ("nwps_category", "forecast_max", "crest") if fl.get(k) is not None}}
        tide = f.get("tide") or {}
        sun = f.get("sun") or []
        spots[sid] = {
            "name": s.get("name"), "region": s.get("region"), "water_type": s.get("water_type"),
            "lat": s.get("lat"), "lon": s.get("lon"), "alerts": s.get("alerts") or [],
            "f": {"water_temp": _v(f.get("water_temp")), "flow": flow, "pressure": f.get("pressure"),
                  "air_trend": f.get("air_temp_trend_72h"), "rain_48h": _v(f.get("rain_48h_in")),
                  "cloud": _v(f.get("cloud_now")), "clarity": f.get("clarity_proxy"),
                  "tide": {"station": tide.get("station"), "label": tide.get("label"), "next": (tide.get("next") or [])[:6]},
                  "moon": f.get("moon"), "sun": sun[:3]},
            "windows": [_window(w) for w in s.get("windows") or []],
        }
    cands, per_day = [], {}
    for c in latest.get("candidates") or []:
        day = str(c.get("window", "")).split("|")[0]
        per_day[day] = per_day.get(day, 0) + 1
        if per_day[day] > PER_DAY:
            continue
        cands.append({k: c.get(k) for k in ("spot", "species", "window", "tier", "confidence", "confidence_note",
                                             "drive_min", "trips", "luca_ok", "reasons", "methods", "interest", "crowded")})
    used_species = {c["species"] for c in cands} | set((kn.species or {}).keys())
    payload = {
        "v": 1,
        "generated_at": latest.get("generated_at"),
        "run_time_et": latest.get("run_time_et"),
        "origin": latest.get("origin"),
        "sources_ok": latest.get("sources_ok"),
        "dnr": latest.get("dnr"),
        "spots": spots,
        "spots_listed": latest.get("spots_listed"),
        "cands": cands,
        "cards": latest.get("cards"),
        "kn": {
            "species": {k: _species_kn(kn.species[k]) for k in sorted(used_species) if k in kn.species},
            "spots": {sid: _spot_kn(kn.spots[sid]) for sid in spots if sid in kn.spots},
            "regs": _regs(kn.regs),
            "regs_checked_on": (kn.regs or {}).get("checked_on"),
            "profile": {k: kn.profile.get(k) for k in ("trip_types", "preferences", "adult_interests", "lower_interest", "luca", "licenses", "setup_overhead_min")},
            "version": latest.get("knowledge_version"),
        },
    }
    return payload


DOC_LIMIT = 240_000  # the 7 Fish database caps one document at 262,144 bytes; keep headroom


def _size(obj) -> int:
    return len(json.dumps(obj, separators=(",", ":"), ensure_ascii=False, default=str).encode())


def split(payload: dict) -> dict:
    """Four documents for the app's `forecast` collection. Every part carries generated_at so the
    page only merges parts from the same run."""
    g = payload.get("generated_at")
    meta = {k: payload.get(k) for k in ("v", "generated_at", "run_time_et", "origin", "sources_ok", "dnr", "spots_listed", "kn")}
    parts = {
        "meta": meta,
        "spots": {"generated_at": g, "spots": payload.get("spots")},
        "cands": {"generated_at": g, "cands": payload.get("cands")},
        "cards": {"generated_at": g, "cards": payload.get("cards")},
    }
    # shed candidates (lowest-ranked per day first) until the part fits
    while _size(parts["cands"]) > DOC_LIMIT and parts["cands"]["cands"]:
        rows = parts["cands"]["cands"]
        by_day = {}
        for r in rows:
            by_day.setdefault(str(r.get("window", "")).split("|")[0], []).append(r)
        biggest = max(by_day.values(), key=len)
        drop = biggest[-1]
        parts["cands"]["cands"] = [r for r in rows if r is not drop]
    # shed hourly-ish window detail if spots is still too big
    if _size(parts["spots"]) > DOC_LIMIT:
        for sp in (parts["spots"]["spots"] or {}).values():
            for w in sp.get("windows") or []:
                (w.get("cond") or {}).pop("short", None)
    for name, part in parts.items():
        part["_bytes"] = _size(part)
    return parts


def write(out_dir, latest: dict, kn) -> int:
    payload = build(latest, kn)
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, default=str)
    Path(out_dir, "app.json").write_text(text)
    app_dir = Path(out_dir, "app")
    app_dir.mkdir(parents=True, exist_ok=True)
    sizes = {}
    for name, part in split(json.loads(text)).items():
        t = json.dumps(part, separators=(",", ":"), ensure_ascii=False)
        Path(app_dir, f"{name}.json").write_text(t)
        sizes[name] = len(t.encode())
    return sizes
