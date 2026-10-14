"""Per-spot features and per-window conditions.

Pure functions (pressure_features, flow_trend, vs_ceiling, clarity_proxy, tide_stage,
wind_relation, ...) are unit-tested directly. `build_spot` assembles them from collected data.

Labels: NWS hourly = forecast; Open-Meteo = modeled (its past hours are model analysis, not
observations); USGS / CO-OPS observed / CBIBS = measured; CO-OPS tide predictions = forecast.
Open-Meteo surface/soil temperature is never requested and never used as water temperature.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, time, timedelta

from .collect import astro
from .collect.nwps import CATS, category_for
from .util import (ET, angle_diff, circular_mean, deg_to_cardinal, hpa_to_inhg, in_range, nearest,
                   not_found, val)

CAT_ORDER = ["none"] + CATS


# ---------------------------------------------------------------- pressure
def pressure_features(series_hpa, at: datetime, cfg: dict) -> dict:
    """series_hpa: [(t, hPa)]. Returns now (inHg), change_24h, class, front."""
    cls_th = cfg.get("class_inhg_24h", 0.06)
    fr_th = cfg.get("front_inhg_24h", 0.10)
    ser = [(t, hpa_to_inhg(v)) for t, v in series_hpa if v is not None]
    cur = nearest(ser, at, timedelta(hours=2))
    prev = nearest(ser, at - timedelta(hours=24), timedelta(hours=2))
    if cur is None:
        return {"now_inhg": None, "change_24h": None, "class": "unknown", "front": "unknown"}
    out = {"now_inhg": round(cur[1], 2)}
    if prev is None:
        out.update({"change_24h": None, "class": "unknown", "front": "unknown"})
        return out
    ch = cur[1] - prev[1]
    cls = "rising" if ch > cls_th else "falling" if ch < -cls_th else "steady"
    front = "steady"
    if ch < -fr_th:
        front = "pre_front_falling"
    elif ch > fr_th:
        # rising fast after a fall within the last 48h
        fell = False
        for h in range(0, 49, 3):
            a = nearest(ser, at - timedelta(hours=h), timedelta(hours=2))
            b = nearest(ser, at - timedelta(hours=h + 24), timedelta(hours=2))
            if a and b and a[1] - b[1] < -cls_th:
                fell = True
                break
        # rising fast itself implies a prior low; require evidence of the fall
        if fell:
            front = "post_front_high_rising"
    out.update({"change_24h": round(ch, 3), "class": cls, "front": front})
    return out


# ---------------------------------------------------------------- flow
def pct_change(series, at, hours):
    cur = nearest(series, at, timedelta(hours=3))
    old = nearest(series, at - timedelta(hours=hours), timedelta(hours=6))
    if cur is None or old is None or not old[1]:
        return None
    return (cur[1] - old[1]) / abs(old[1])


def flow_trend(series, at, hours=72, th=0.10) -> str:
    ch = pct_change(series, at, hours)
    if ch is None:
        # fall back to earliest point if history is shorter than requested
        pts = [p for p in series if p[0] <= at]
        if len(pts) >= 2 and pts[0][1]:
            ch = (pts[-1][1] - pts[0][1]) / abs(pts[0][1])
        else:
            return "unknown"
    return "rising" if ch > th else "falling" if ch < -th else "steady"


def vs_ceiling(value, ceiling, near_fraction=0.85) -> str:
    if value is None or ceiling is None:
        return "unknown"
    if value > ceiling:
        return "over"
    if value >= near_fraction * ceiling:
        return "near"
    return "under"


def max_category(cats: list[str]) -> str:
    known = [c for c in cats if c in CAT_ORDER]
    if not known:
        return "unknown"
    return max(known, key=CAT_ORDER.index)


def cat_at_least(cat: str, floor: str) -> bool:
    return cat in CAT_ORDER and floor in CAT_ORDER and CAT_ORDER.index(cat) >= CAT_ORDER.index(floor)


# ---------------------------------------------------------------- clarity
def clarity_proxy(rain_48h, flow_change_48h, flow_trend_72h, turbidity=None, cfg=None) -> dict:
    cfg = cfg or {}
    if turbidity is not None:
        if turbidity >= cfg.get("turbidity_muddy_ntu", 25):
            return {"v": "likely_muddy", "label": "measured", "basis": f"buoy turbidity {turbidity:.0f}"}
        if turbidity < cfg.get("turbidity_clear_ntu", 10):
            return {"v": "likely_clear", "label": "measured", "basis": f"buoy turbidity {turbidity:.0f}"}
    muddy_rain = cfg.get("muddy_rain_48h_in", 0.75)
    clear_rain = cfg.get("clear_rain_48h_in", 0.1)
    muddy_rise = cfg.get("muddy_flow_rise_48h", 0.30)
    if (rain_48h is not None and rain_48h >= muddy_rain) or (flow_change_48h is not None and flow_change_48h > muddy_rise):
        return {"v": "likely_muddy", "label": "reasoning", "basis": _basis(rain_48h, flow_change_48h)}
    if rain_48h is not None and rain_48h < clear_rain and flow_trend_72h in ("steady", "falling"):
        return {"v": "likely_clear", "label": "reasoning", "basis": _basis(rain_48h, flow_change_48h)}
    if rain_48h is not None and rain_48h < clear_rain and flow_trend_72h == "n/a":  # no-flow water (bay)
        return {"v": "likely_clear", "label": "reasoning", "basis": _basis(rain_48h, None)}
    return {"v": "unknown", "label": "reasoning", "basis": _basis(rain_48h, flow_change_48h)}


def _basis(rain, ch):
    parts = []
    if rain is not None:
        parts.append(f"rain 48h {rain:.2f} in")
    if ch is not None:
        parts.append(f"flow {ch * 100:+.0f}% in 48h")
    return ", ".join(parts) or "no rain or flow data"


# ---------------------------------------------------------------- tide
def tide_stage(hilo: list[dict], t: datetime, slack_min: int = 45) -> str:
    """incoming / outgoing / slack (±slack_min of a turn) / unknown."""
    if not hilo:
        return "unknown"
    prev = next_ = None
    for h in hilo:
        if h["t"] <= t:
            prev = h
        elif next_ is None:
            next_ = h
    for h in (prev, next_):
        if h is not None and abs((h["t"] - t).total_seconds()) <= slack_min * 60:
            return "slack"
    if prev is not None:
        return "incoming" if prev.get("type") == "L" else "outgoing" if prev.get("type") == "H" else "unknown"
    if next_ is not None:
        return "outgoing" if next_.get("type") == "L" else "incoming" if next_.get("type") == "H" else "unknown"
    return "unknown"


def window_tide(hilo, start, end, slack_min=45) -> dict:
    stages = []
    t = start
    while t < end:
        stages.append(tide_stage(hilo, t, slack_min))
        t += timedelta(minutes=15)
    turns = [{"t": h["t"], "type": h.get("type"), "ft": h.get("v")} for h in hilo if start <= h["t"] < end]
    known = [s for s in stages if s != "unknown"]
    dom = Counter(known).most_common(1)[0][0] if known else "unknown"
    return {"dominant": dom, "start": stages[0] if stages else "unknown", "turns": turns}


# ---------------------------------------------------------------- wind
def wind_relation(wind_from_deg, bank_faces_deg) -> str:
    """onshore = wind blowing toward the angler, i.e. FROM the direction the angler faces (±60°)."""
    if wind_from_deg is None or bank_faces_deg is None:
        return "unknown"
    if angle_diff(wind_from_deg, bank_faces_deg) <= 60:
        return "onshore"
    if angle_diff(wind_from_deg, (bank_faces_deg + 180) % 360) <= 60:
        return "offshore"
    return "cross"


# ---------------------------------------------------------------- water temp
def pick_water_temp(cands: list[dict], at: datetime, max_dist=25, max_age_h=36) -> dict:
    """cands: [{v, src, dist_mi, at}] measured readings. Nearest valid within limits."""
    ok = []
    for c in cands:
        if c.get("v") is None or c.get("at") is None:
            continue
        if c.get("dist_mi") is not None and c["dist_mi"] > max_dist:
            continue
        if (at - c["at"]).total_seconds() > max_age_h * 3600:
            continue
        ok.append(c)
    if not ok:
        return not_found("degF", note="no measured water temp within %d mi / %d h" % (max_dist, max_age_h))
    best = min(ok, key=lambda c: (c.get("dist_mi") if c.get("dist_mi") is not None else 99, -(c["at"].timestamp())))
    return val(best["v"], "degF", "measured", best["src"], best.get("dist_mi"), best["at"],
               trend_72h=best.get("trend_72h"))


def temp_trend(series, at, hours=72, th=2.0):
    cur = nearest(series, at, timedelta(hours=3))
    if cur is None:
        return None
    old = nearest(series, at - timedelta(hours=hours), timedelta(hours=8))
    if old is None:
        pts = [p for p in series if p[0] <= at]
        if len(pts) < 2 or (pts[-1][0] - pts[0][0]) < timedelta(hours=36):
            return None
        old = pts[0]
    d = cur[1] - old[1]
    return {"change_f": round(d, 1), "class": "warming" if d > th else "cooling" if d < -th else "steady"}


# ---------------------------------------------------------------- windows
def make_windows(days: list[dict], now: datetime, after_dark: str) -> list[dict]:
    out = []
    for a in days:
        if "sunrise" not in a or "sunset" not in a:
            continue
        d = a["date"]
        sr, ss = a["sunrise"], a["sunset"]
        cd, ck = a.get("civil_dawn") or sr - timedelta(minutes=30), a.get("civil_dusk") or ss + timedelta(minutes=30)
        end_of_day = datetime.combine(datetime.fromisoformat(d).date(), time(23, 59), tzinfo=ET)
        spans = [("dawn", cd, sr + timedelta(hours=3)),
                 ("day", sr + timedelta(hours=3), ss - timedelta(hours=2)),
                 ("dusk", ss - timedelta(hours=2), ck)]
        if after_dark == "allowed":
            spans.append(("night", ck, end_of_day))
        for kind, s, e in spans:
            if e <= now or e <= s:
                continue
            out.append({"id": f"{d}|{kind}", "date": d, "kind": kind, "start": s, "end": e,
                        "in_progress": s <= now, "sunset": ss, "sunrise": sr})
    return out


# ---------------------------------------------------------------- assemble
def build_spot(spot: dict, data: dict, now: datetime, gcfg: dict, n_days: int = 3) -> dict:
    """data keys: nws, om, usgs, nwps, coops, cbibs (any may be None)."""
    st = spot.get("stations") or {}
    nws, om = data.get("nws") or {}, data.get("om") or {}
    usgs, nwps, coops, cbibs = data.get("usgs"), data.get("nwps"), data.get("coops"), data.get("cbibs")
    om_s = (om.get("series") or {})
    lat, lon = spot["lat"], spot["lon"]
    feats: dict = {}

    # astro
    days = [astro.day(lat, lon, (now.astimezone(ET) + timedelta(days=i)).date()) for i in range(n_days)]

    # pressure
    pf = pressure_features(om_s.get("pressure_msl") or [], now, gcfg.get("pressure", {}))
    pf.update({"label": "modeled" if pf.get("class") != "unknown" else "not_found", "src": "Open-Meteo"})
    feats["pressure"] = pf

    # air temp trend / rain / cloud
    at_tr = temp_trend(om_s.get("temperature_2m") or [], now, 72, 5.0)
    feats["air_temp_trend_72h"] = ({**at_tr, "label": "modeled", "src": "Open-Meteo"} if at_tr
                                   else not_found("degF", "Open-Meteo"))
    rain_pts = in_range(om_s.get("precipitation") or [], now - timedelta(hours=48), now)
    rain48 = round(sum(v for _, v in rain_pts), 2) if len(rain_pts) >= 36 else None
    feats["rain_48h_in"] = val(rain48, "in", "modeled", "Open-Meteo", at=now)
    cl = nearest(om_s.get("cloud_cover") or [], now)
    feats["cloud_now"] = val(cl[1] if cl else None, "%", "modeled", "Open-Meteo", at=cl[0] if cl else None)

    # water temp
    wt_cands = []
    if usgs and usgs.get("water_temp"):
        s = usgs["water_temp"]
        wt_cands.append({"v": s[-1][1], "at": s[-1][0], "src": f"USGS {usgs['site']}",
                         "dist_mi": (st.get("usgs") or {}).get("distance_mi"), "trend_72h": temp_trend(s, now)})
    if coops and coops.get("water_temp"):
        s = coops["water_temp"]
        wt_cands.append({"v": s[-1][1], "at": s[-1][0], "src": f"CO-OPS {coops['station']}",
                         "dist_mi": (st.get("coops") or {}).get("distance_mi"), "trend_72h": temp_trend(s, now)})
    if cbibs and (cbibs.get("values") or {}).get("water_temp"):
        w = cbibs["values"]["water_temp"]
        wt_cands.append({"v": w["v"], "at": w["at"], "src": f"CBIBS {cbibs['station']}",
                         "dist_mi": (st.get("cbibs") or {}).get("distance_mi"), "trend_72h": None})
    for ex in data.get("extra") or []:
        ed, edef = ex.get("data") or {}, ex.get("def") or {}
        if ex["kind"] in ("usgs", "coops") and ed.get("water_temp"):
            s = ed["water_temp"]
            tag = f"USGS {ed.get('site')}" if ex["kind"] == "usgs" else f"CO-OPS {ed.get('station')}"
            wt_cands.append({"v": s[-1][1], "at": s[-1][0], "src": tag,
                             "dist_mi": edef.get("distance_mi"), "trend_72h": temp_trend(s, now)})
        elif ex["kind"] == "cbibs" and ((ed.get("values") or {}).get("water_temp")):
            w = ed["values"]["water_temp"]
            wt_cands.append({"v": w["v"], "at": w["at"], "src": f"CBIBS {ed.get('station')}",
                             "dist_mi": edef.get("distance_mi"), "trend_72h": None})
    wt = gcfg.get("water_temp", {})
    feats["water_temp"] = pick_water_temp(wt_cands, now, wt.get("max_station_dist_mi", 25), wt.get("max_age_h", 36))

    # flow
    feats["flow"] = _flow(spot, usgs, nwps, now, gcfg)

    # clarity
    turb = ((cbibs or {}).get("values") or {}).get("turbidity", {}).get("v") if cbibs else None
    fl = feats["flow"]
    feats["clarity_proxy"] = clarity_proxy(rain48, fl.get("change_48h"), fl.get("trend_72h", "n/a"), turb,
                                           gcfg.get("clarity", {}))
    if cbibs and cbibs.get("values"):
        feats["buoy"] = {k: val(v["v"], v.get("unit"), "measured", f"CBIBS {cbibs['station']}",
                                (st.get("cbibs") or {}).get("distance_mi"), v.get("at"))
                         for k, v in cbibs["values"].items()}

    # tide
    hilo = (coops or {}).get("hilo") or []
    feats["tide"] = {"station": (coops or {}).get("station"), "label": "forecast" if hilo else "not_found",
                     "next": [{"t": h["t"], "type": h.get("type"), "ft": h.get("v")} for h in hilo if h["t"] >= now][:6]}

    # moon (today)
    d0 = days[0]
    feats["moon"] = {"phase": d0.get("moon_phase"), "illum_pct": d0.get("moon_illum_pct"),
                     "transit": d0.get("moon_transit"), "label": "modeled", "src": "ephem"}
    feats["sun"] = [{"date": a["date"], "civil_dawn": a.get("civil_dawn"), "sunrise": a.get("sunrise"),
                     "sunset": a.get("sunset"), "civil_dusk": a.get("civil_dusk"),
                     "moon_phase": a.get("moon_phase"), "moon_illum_pct": a.get("moon_illum_pct"),
                     "moon_transit": a.get("moon_transit")} for a in days]

    # windows + conditions
    after_dark = str(((spot.get("access") or {}).get("after_dark")) or "not_verified").lower()
    windows = make_windows(days, now, after_dark)
    hourly = nws.get("hourly") or []
    for w in windows:
        w["conditions"] = _window_conditions(spot, w, hourly, om_s, hilo, feats, nwps, gcfg, days)

    # compact hourly for the window days only
    last = max((w["end"] for w in windows), default=now)
    feats["hourly"] = [{"t": h["t"], "temp_f": _r(h["temp_f"]), "wind_mph": _r(h["wind_mph"]),
                        "gust_mph": _r(h["gust_mph"]), "pop": _r(h["pop"]), "short": h["short"][:40]}
                       for h in hourly if now - timedelta(hours=1) <= h["t"] <= last]
    feats["weather_label"] = "forecast" if hourly else "not_found"
    return {"features": feats, "windows": windows, "alerts": nws.get("alerts") or [],
            "alerts_checked": bool(nws.get("ok_alerts"))}


def _r(x, n=0):
    if x is None:
        return None
    return round(x) if n == 0 else round(x, n)


def _flow(spot, usgs, nwps, now, gcfg) -> dict:
    wtype = str(spot.get("water_type") or "river")
    st = spot.get("stations") or {}
    fcfg = gcfg.get("flow", {})
    ceiling = spot.get("flow_ceiling") or {}
    c_val = ceiling.get("value") if isinstance(ceiling.get("value"), (int, float)) else None
    c_unit = str(ceiling.get("unit") or "cfs").lower()
    out: dict = {"applies": wtype in ("river", "tidal-river")}
    if wtype not in ("river", "tidal-river") and not usgs and not nwps:
        out.update({"trend_72h": "n/a", "vs_ceiling": "n/a", "current": val(None, "cfs", src=None, note="n/a")})
        out["applies"] = False
        return out
    # current flow + series
    q_series, q_src, q_label = [], None, "not_found"
    if usgs and usgs.get("discharge"):
        q_series, q_src, q_label = usgs["discharge"], f"USGS {usgs['site']}", "measured"
    elif nwps and (nwps.get("observed") or {}).get("flow"):
        q_series, q_src, q_label = nwps["observed"]["flow"], f"NWPS {nwps['lid']}", "measured"
    h_series, h_src = [], None
    if usgs and usgs.get("gage_height"):
        h_series, h_src = usgs["gage_height"], f"USGS {usgs['site']}"
    elif nwps and (nwps.get("observed") or {}).get("stage"):
        h_series, h_src = nwps["observed"]["stage"], f"NWPS {nwps['lid']}"
    dist = (st.get("usgs") or {}).get("distance_mi") if (usgs and q_src and q_src.startswith("USGS")) else (st.get("nwps") or {}).get("distance_mi")
    cur_q = q_series[-1] if q_series else None
    cur_h = h_series[-1] if h_series else None
    out["current"] = val(cur_q[1] if cur_q else None, "cfs", q_label, q_src, dist, cur_q[0] if cur_q else None)
    out["stage"] = val(cur_h[1] if cur_h else None, "ft", "measured" if cur_h else "not_found", h_src, dist,
                       cur_h[0] if cur_h else None)
    base = q_series or h_series
    out["trend_72h"] = flow_trend(base, now) if base else "unknown"
    ch48 = pct_change(base, now, 48) if base else None
    out["change_48h"] = round(ch48, 3) if ch48 is not None else None

    # ceiling
    near = fcfg.get("near_fraction", 0.85)
    cats = (nwps or {}).get("categories") or {}
    action_stage = (cats.get("action") or {}).get("stage")
    if c_val is not None:
        cur_for = (cur_h[1] if cur_h else None) if c_unit in ("ft", "feet") else (cur_q[1] if cur_q else None)
        out["ceiling"] = {"v": c_val, "unit": c_unit, "source": ceiling.get("source") or "spot file"}
        out["vs_ceiling"] = vs_ceiling(cur_for, c_val, near)
    elif action_stage is not None and fcfg.get("ceiling_fallback") == "nwps_action_stage":
        out["ceiling"] = {"v": action_stage, "unit": "ft", "source": f"NWPS {nwps['lid']} action stage (fallback; ask Matt)"}
        out["vs_ceiling"] = vs_ceiling(cur_h[1] if cur_h else None, action_stage, near)
    else:
        out["ceiling"] = {"v": None, "unit": c_unit, "source": ceiling.get("source") or "not found"}
        out["vs_ceiling"] = "unknown"

    # NWPS categories
    if nwps and nwps.get("ok"):
        obs_cat = ((nwps.get("status") or {}).get("observed") or {}).get("category")
        obs_cat = str(obs_cat).lower() if obs_cat else category_for(cur_h[1] if cur_h else None, cats)
        if obs_cat in ("no_flooding", "no flooding", "normal"):
            obs_cat = "none"
        fc_stage = (nwps.get("forecast") or {}).get("stage") or []
        fc_cat = max_category([category_for(v, cats) for _, v in fc_stage]) if fc_stage else "unknown"
        crest = max(fc_stage, key=lambda x: x[1]) if fc_stage else None
        out["nwps"] = {"lid": nwps.get("lid"), "category_now": obs_cat, "forecast_max_category": fc_cat,
                       "crest": {"t": crest[0], "stage_ft": round(crest[1], 2), "label": "forecast"} if crest else None,
                       "action_stage_ft": action_stage, "minor_stage_ft": (cats.get("minor") or {}).get("stage")}
    return out


def _window_conditions(spot, w, hourly, om_s, hilo, feats, nwps, gcfg, days) -> dict:
    s, e = w["start"], w["end"]
    hrs = [h for h in hourly if s - timedelta(minutes=59) < h["t"] < e]
    cond: dict = {}
    if hrs:
        winds = [h["wind_mph"] for h in hrs if h["wind_mph"] is not None]
        gusts = [h["gust_mph"] for h in hrs if h["gust_mph"] is not None]
        dirs = [h["wind_dir_deg"] for h in hrs]
        temps = [h["temp_f"] for h in hrs if h["temp_f"] is not None]
        pops = [h["pop"] for h in hrs if h["pop"] is not None]
        mdir = circular_mean(dirs)
        cond["wind"] = {"mean_mph": _r(sum(winds) / len(winds)) if winds else None,
                        "max_gust_mph": _r(max(gusts)) if gusts else None,
                        "gust_src": "NWS" if gusts else None,
                        "dir_deg": _r(mdir), "dir": deg_to_cardinal(mdir),
                        "relation": wind_relation(mdir, spot.get("bank_faces_deg")), "label": "forecast"}
        cond["air_temp_f"] = {"min": _r(min(temps)), "max": _r(max(temps)), "label": "forecast"} if temps else None
        cond["pop_max"] = _r(max(pops)) if pops else None
        cond["short"] = sorted(set(h["short"] for h in hrs if h["short"]))[:4]
        cond["weather_checked"] = True
    else:
        cond["weather_checked"] = False
        cond["short"] = []
        cond["wind"] = {"mean_mph": None, "max_gust_mph": None, "dir": None, "relation": "unknown", "label": "not_found"}
    # Open-Meteo gust fallback
    if cond["wind"].get("max_gust_mph") is None:
        og = [v for _, v in in_range(om_s.get("wind_gusts_10m") or [], s, e)]
        if og:
            cond["wind"]["max_gust_mph"] = _r(max(og))
            cond["wind"]["gust_src"] = "Open-Meteo (modeled)"
    if cond["wind"].get("dir") is None:
        od = [v for _, v in in_range(om_s.get("wind_direction_10m") or [], s, e)]
        mdir = circular_mean(od)
        if mdir is not None:
            cond["wind"]["dir_deg"], cond["wind"]["dir"] = _r(mdir), deg_to_cardinal(mdir)
            cond["wind"]["relation"] = wind_relation(mdir, spot.get("bank_faces_deg"))
    # cloud / light
    cc = [v for _, v in in_range(om_s.get("cloud_cover") or [], s, e)]
    cloud = sum(cc) / len(cc) if cc else None
    cond["cloud_pct"] = _r(cloud)
    cond["light"] = {"type": w["kind"], "overcast": bool(cloud is not None and cloud >= 75)}
    # front at the window (forecast pressure)
    mid = s + (e - s) / 2
    pw = pressure_features(om_s.get("pressure_msl") or [], mid, gcfg.get("pressure", {}))
    cond["front"] = pw.get("front", "unknown")
    cond["pressure_class"] = pw.get("class", "unknown")
    # tide
    if hilo:
        cond["tide"] = window_tide(hilo, s, e, gcfg.get("tide", {}).get("slack_min", 45))
    # flow in window (NWPS forecast if it covers the window)
    fl = feats.get("flow") or {}
    if fl.get("applies"):
        cond["flow"] = _window_flow(fl, nwps, s, e, gcfg)
    # moon
    day = next((a for a in days if a["date"] == w["date"]), {})
    cond["moon"] = {"phase": day.get("moon_phase"), "illum_pct": day.get("moon_illum_pct"),
                    "transit": day.get("moon_transit"),
                    "transit_in_window": bool(day.get("moon_transit") and s <= day["moon_transit"] < e)}
    return cond


def _window_flow(fl, nwps, s, e, gcfg):
    near = gcfg.get("flow", {}).get("near_fraction", 0.85)
    ceiling = fl.get("ceiling") or {}
    c_val, c_unit = ceiling.get("v"), str(ceiling.get("unit") or "cfs")
    fc = (nwps or {}).get("forecast") or {}
    use_stage = c_unit in ("ft", "feet")
    series = fc.get("stage" if use_stage else "flow") or []
    pts = [v for t, v in series if s - timedelta(hours=3) <= t <= e + timedelta(hours=3)]
    if pts:
        v, label, src = max(pts), "forecast", f"NWPS {(nwps or {}).get('lid')}"
    else:
        cur = fl.get("stage" if use_stage else "current") or {}
        v, label, src = cur.get("v"), cur.get("label", "not_found"), cur.get("src")
    cats = (nwps or {}).get("categories") or {}
    st_pts = [v2 for t, v2 in (fc.get("stage") or []) if s - timedelta(hours=3) <= t <= e + timedelta(hours=3)]
    cat = max_category([category_for(x, cats) for x in st_pts]) if st_pts and cats else \
        ((fl.get("nwps") or {}).get("category_now") or "unknown")
    return {"v": _r(v, 2) if isinstance(v, float) and v < 100 else _r(v), "unit": "ft" if use_stage else "cfs",
            "label": label if v is not None else "not_found", "src": src,
            "vs_ceiling": vs_ceiling(v, c_val, near), "nwps_category": cat}
