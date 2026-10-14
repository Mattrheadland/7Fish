"""Baseline (code-built) cards for every app combo: when × trip × luca, target = any.

Card fields follow engine/schema/card.schema.json. source = "engine".
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from .candidates import TIER_RANK
from .knowledge import norm_status
from .util import ET, window_text

WHENS = ["next3h", "tomorrow_am", "weekend"]
TRIPS = ["quick", "half", "full"]
LUCAS = [False, True]
LABEL_PRI = {"measured": 0, "report": 1, "forecast": 2, "modeled": 3, "reasoning": 4, "not_found": 5}


# ---------------------------------------------------------------- selection
def window_matches(when: str, w: dict, now: datetime) -> bool:
    now = now.astimezone(ET)
    s, e = w["start"], w["end"]
    if when == "next3h":
        return s < now + timedelta(hours=3) and e > now
    d = datetime.fromisoformat(w["date"]).date()
    if when == "tomorrow_am":
        return d == (now + timedelta(days=1)).date() and s.astimezone(ET).time() < time(12, 0)
    if when == "weekend":
        if d.weekday() not in (5, 6):
            return False
        # this coming weekend only (or the current one, if today is Sat/Sun)
        return (d - now.date()).days <= 6
    return False


def pick(cands: list[dict], when: str, trip: str, luca: bool, now: datetime) -> list[dict]:
    out = [c for c in cands
           if trip in c["trips"] and (c["luca_ok"] or not luca) and window_matches(when, c["_w"], now)]
    return out  # already sorted by candidates.sort_key


def verdict_for(c: dict | None, gust_limit=None, near_mph=5) -> tuple[str, str | None]:
    """Return (verdict, condition_kind). condition_kind: flow_near | gust_near | low_conf | None."""
    if c is None:
        return "SKIP", None
    tier, conf = c["tier"], c["confidence"]
    cond = c["_w"].get("conditions") or {}
    flow_near = ((cond.get("flow") or {}).get("vs_ceiling") == "near")
    g = (cond.get("wind") or {}).get("max_gust_mph")
    gust_near = g is not None and gust_limit is not None and g >= gust_limit - near_mph
    if tier in ("Prime", "Good") and conf != "low":
        return "GO", None
    if tier in ("Prime", "Good") and conf == "low":
        return "GO IF", ("flow_near" if flow_near else "gust_near" if gust_near else "low_conf")
    if tier == "Fair" and (flow_near or gust_near):
        return "GO IF", ("flow_near" if flow_near else "gust_near")
    return "SKIP", None


# ---------------------------------------------------------------- text helpers
def _sp_name(kn, key):
    return (kn.species.get(key) or {}).get("name") or key.replace("-", " ")


def _method(kn, skey, cond):
    methods = [m for m in (kn.species.get(skey) or {}).get("methods") or [] if isinstance(m, dict)]
    if not methods:
        return None, None
    return methods[0], {m.get("id"): m for m in methods}


def _condition_text(kind, c, spot, kn):
    cond = c["_w"].get("conditions") or {}
    if kind == "flow_near":
        fl = cond.get("flow") or {}
        ceil = ((spot.get("flow_ceiling") or {}).get("value"))
        unit = (spot.get("flow_ceiling") or {}).get("unit") or fl.get("unit")
        src = fl.get("src") or "the gauge"
        if ceil is None:
            return f"Only if {src} is still below its action stage when you leave."
        return f"Only if {src} reads under {ceil:g} {unit} when you leave."
    if kind == "gust_near":
        lim = spot.get("wind_gust_limit_mph") or kn.gates.get("wind", {}).get("default_gust_limit_mph", 30)
        return f"Only if the NWS hourly still shows gusts under {lim:g} mph at the spot before you leave."
    return "Only if the water looks fishable on arrival (not muddy or blown out); no gauge or fresh report backs this call."


def _rules(kn, skey, region, spot):
    out = []
    checked = str(kn.regs.get("checked_on") or "not found")
    for e in kn.regs_for(skey, region):
        harvest = e.get("harvest") or []
        if harvest:
            parts = []
            for h in harvest[:2]:
                if isinstance(h, dict):
                    parts.append(" ".join(str(x) for x in [f"{h.get('start')}–{h.get('end')}" if h.get('start') else None,
                                                             h.get("size"), h.get("creel")] if x and x != "None"))
            txt = f"{e.get('area', 'Area')}: harvest " + "; ".join(p for p in parts if p)
        else:
            txt = f"{e.get('area', 'Area')}: catch-and-release only"
        if e.get("warning"):
            txt += f" (warning: {e['warning']})"
        out.append({"text": txt[:240], "checked_on": checked, "src": e.get("src") or "not found"})
    if not out:
        out.append({"text": "Rules for this species and water not found in regs.yaml; check DNR before keeping fish.",
                    "checked_on": checked, "src": "not found"})
    j = spot.get("jurisdiction") or {}
    for f in (j.get("flags") or [])[:2]:
        out.append({"text": str(f)[:240], "checked_on": checked, "src": j.get("src") or "spot file"})
    if j.get("license"):
        out.append({"text": f"License: {j['license']} (per Matt; not verified)", "checked_on": checked, "src": "spot file"})
    return out


def _pqa(spot, skey):
    se = (spot.get("species") or {}).get(skey) or {}
    acc = spot.get("access") or {}
    ev = (se.get("evidence") or [{}])[0] if isinstance(se.get("evidence"), list) and se.get("evidence") else {}
    ev_txt = (ev.get("text") or "")[:160] if isinstance(ev, dict) else ""
    return {
        "presence": {"status": norm_status(se.get("presence")), "note": ev_txt or "per spot file"},
        "quality": {"status": norm_status(se.get("quality")), "note": "per spot file"},
        "access": {"status": norm_status(acc.get("status")),
                   "note": ((acc.get("parking") or {}).get("text") if isinstance(acc.get("parking"), dict) else None) or "per spot file"},
    }


def _drivers(c):
    rs = sorted(c["reasons"], key=lambda r: (LABEL_PRI.get(r.get("label"), 9)))
    out = []
    for r in rs[:3]:
        d = {"text": r["text"][:160], "label": r.get("label", "reasoning")}
        if r.get("src"):
            d["src"] = str(r["src"])[:120]
        out.append(d)
    return out


def _flips(c, spot, kn):
    cond = c["_w"].get("conditions") or {}
    lim = spot.get("wind_gust_limit_mph") or kn.gates.get("wind", {}).get("default_gust_limit_mph", 30)
    parts = [f"thunder or a warning in the forecast", f"gusts over {lim:g} mph"]
    if (cond.get("flow") or {}).get("vs_ceiling") not in (None, "unknown"):
        parts.append("flow over the ceiling")
    if c["_info"].get("band") is None:
        parts.append("a water temp reading outside the species' active range")
    return "SKIP if: " + ", ".join(parts) + "."


def _uncertainty(c, feats):
    if (feats.get("water_temp") or {}).get("label") != "measured":
        return "No measured water temperature near this spot."
    if not any(r.get("label") == "report" for r in c["reasons"]):
        return "No recent report of this species here; the call rests on conditions and season."
    return "Season calendar and preferences are partly reasoning, not measured response."


def _fishing_min(c, trip, kn, spot_windows):
    nominal = ((kn.profile.get("trip_types") or {}).get(trip) or {}).get("fishing_min") or 120
    w = c["_w"]
    start = (w.get("clip") or {}).get("start", w["start"])
    # contiguous passing windows on the same date bound the legal fishing time
    end = (w.get("clip") or {}).get("end", w["end"])
    for o in sorted(spot_windows, key=lambda x: x["start"]):
        if o["date"] == w["date"] and o["start"] >= w["start"] and all(gg["pass"] for gg in o["gates"]):
            if o["start"] <= end + timedelta(minutes=1):
                end = max(end, (o.get("clip") or {}).get("end", o["end"]))
    avail = max(0, int((end - start).total_seconds() // 60))
    return int(5 * round(min(nominal, avail) / 5))


# ---------------------------------------------------------------- build
def build_card(kn, combo, picks, spot_results, now) -> dict:
    when, trip, luca = combo
    top = picks[0] if picks else None
    spot = kn.spots.get(top["spot"]) if top else None
    lim = None
    if spot:
        lim = spot.get("wind_gust_limit_mph") or kn.gates.get("wind", {}).get("default_gust_limit_mph", 30)
    verdict, ckind = verdict_for(top, lim, kn.gates.get("wind", {}).get("near_limit_mph", 5))
    if verdict == "SKIP":
        return _skip_card(kn, combo, top, now)
    skey, sid = top["species"], top["spot"]
    feats = spot_results[sid]["features"]
    w = top["_w"]
    ws, we = (w.get("clip") or {}).get("start", w["start"]), (w.get("clip") or {}).get("end", w["end"])
    m, mmap = _method(kn, skey, w.get("conditions"))
    alt = (mmap or {}).get((m or {}).get("switch_to")) if m else None
    sname, spname = _sp_name(kn, skey), spot.get("name", sid)
    kind_word = {"dawn": "Dawn", "day": "Midday", "dusk": "Dusk", "night": "Night"}[w["kind"]]
    headline = f"{kind_word} {sname.lower()} at {spname}. {top['tier']} window, {top['confidence']} confidence."
    if verdict == "GO IF":
        headline = f"{kind_word} {sname.lower()} at {spname}, if conditions check out."
    backup = next((c for c in picks[1:] if c["spot"] != sid or c["species"] != skey), None)
    fishing = _fishing_min(top, trip, kn, spot_results[sid]["windows"])
    overhead = kn.profile.get("setup_overhead_min", 20)
    card = {
        "verdict": verdict,
        "headline": headline[:140],
        "condition": _condition_text(ckind, top, spot, kn) if verdict == "GO IF" else None,
        "play": {
            "species_key": skey, "species": sname, "spot_id": sid, "spot": spname,
            "window_id": w["id"], "window_text": window_text(ws, we),
            "method": (m or {}).get("id", "not found").replace("-", " "),
        },
        "rig_line": (m or {}).get("rig_line"),
        "details": {
            "named_target": None,
            "drivers": _drivers(top),
            "confidence": top["confidence"],
            "confidence_note": top.get("confidence_note", ""),
            "pqa": _pqa(spot, skey),
            "rules": _rules(kn, skey, spot.get("region"), spot),
            "rig": {"primary": (m or {}).get("rig_line") or "not found",
                    "alternate": (alt or {}).get("rig_line") or "not found",
                    "switch_trigger": (m or {}).get("switch_trigger") or "not found",
                    "gear_note": (m or {}).get("gear_note") or "not found"},
            "backup": ({"text": f"{_sp_name(kn, backup['species'])} at {kn.spots[backup['spot']].get('name')}, "
                                f"{window_text(backup['_w']['start'], backup['_w']['end'])} ({backup['tier']})",
                        "spot_id": backup["spot"], "species_key": backup["species"], "window_id": backup["window"]}
                       if backup else None),
            "flips_it": _flips(top, spot, kn),
            "time": {"drive_min": top["drive_min"], "fishing_min": fishing,
                     "away_min": 2 * top["drive_min"] + fishing + overhead},
            "skip": None,
            "uncertainty": _uncertainty(top, feats),
        },
        "source": "engine",
    }
    if luca:
        card["details"]["uncertainty"] += " Luca mode: finish by sunset."
    return card


def _skip_card(kn, combo, top, now) -> dict:
    when, trip, luca = combo
    reason = _skip_reason(when, trip, luca, top, now)
    closest = "No passing candidate for this request."
    if top is not None:
        closest = (f"{_sp_name(kn, top['species'])} at {kn.spots[top['spot']].get('name')}, "
                   f"{window_text(top['_w']['start'], top['_w']['end'])}: {top['tier']}, {top['confidence']} confidence.")
    return {
        "verdict": "SKIP",
        "headline": reason[:140],
        "condition": None,
        "play": None,
        "rig_line": None,
        "details": {
            "named_target": None, "drivers": [],
            "confidence": top["confidence"] if top else "low",
            "confidence_note": top.get("confidence_note", "") if top else "no candidates passed the gates",
            "skip": {"reason": reason, "closest_miss": closest[:240]},
            "backup": None,
            "uncertainty": "A SKIP from thin data is low confidence, not proof of a poor bite.",
        },
        "source": "engine",
    }


def _skip_reason(when, trip, luca, top, now):
    if top is None:
        if when == "weekend":
            d = now.astimezone(ET).date()
            sat = d + timedelta(days=(5 - d.weekday()) % 7)
            return (f"No passing weekend window yet. Sat {sat.strftime('%b')} {sat.day}, {sat.year} may be beyond the "
                    f"3-day forecast; later runs will cover it.")
        extra = " that suits Luca" if luca else ""
        return f"Nothing passes the gates{extra} for a {trip} trip in this window."
    return f"Best available is {top['tier']} with {top['confidence']} confidence. Not worth the trip."


def build_all(kn, cands, spot_results, now) -> dict:
    cards = {}
    for when in WHENS:
        for trip in TRIPS:
            for luca in LUCAS:
                picks = pick(cands, when, trip, luca, now)
                key = f"{when}|{trip}|{'true' if luca else 'false'}"
                cards[key] = build_card(kn, (when, trip, luca), picks, spot_results, now)
    return cards
