import json
from datetime import timedelta

from conftest import NOW

from engine import candidates as C
from engine import cards as K

SPECIES = {
    "temp_bands_f": [{"band": "inactive", "max": 45}, {"band": "slow", "min": 45, "max": 55},
                     {"band": "active", "min": 55, "max": 65}, {"band": "peak", "min": 65, "max": 75},
                     {"band": "stressed", "min": 75}],
    "prefs": {"flow": {"rising": "plus", "falling": "minus", "high_muddy": "minus"},
              "light": {"dawn": "plus", "day": "minus", "dusk": "plus", "overcast": "plus"},
              "tide": {"incoming": "plus", "outgoing": "plus", "slack": "minus"},
              "front": {"pre_front_falling": "plus", "post_front_high_rising": "minus", "steady": "neutral"}},
}


def feats(wt=None, trend="steady", clarity="unknown"):
    f = {"water_temp": {"v": wt, "label": "measured" if wt is not None else "not_found", "src": "USGS x"},
         "flow": {"trend_72h": trend, "current": {"v": 1000, "label": "measured", "src": "USGS x"}},
         "clarity_proxy": {"v": clarity, "label": "reasoning", "basis": "test"},
         "tide": {"label": "not_found"}}
    return f


def cond(light="dawn", front="steady", overcast=False, tide=None):
    c = {"light": {"type": light, "overcast": overcast}, "front": front}
    if tide:
        c["tide"] = {"dominant": tide}
    return c


def test_temp_band_edges():
    assert C.temp_band(SPECIES, 44.9) == "inactive"
    assert C.temp_band(SPECIES, 45) == "slow"
    assert C.temp_band(SPECIES, 70) == "peak"
    assert C.temp_band(SPECIES, 90) == "stressed"
    assert C.temp_band(SPECIES, None) is None
    assert C.temp_band({}, 60) is None


def test_tier_base_and_steps():
    t, _, _ = C.tier_for(SPECIES, "good", cond("day"), feats(60), "river")
    assert t == "Fair"                                  # day light minus
    t, _, _ = C.tier_for(SPECIES, "good", cond("dawn"), feats(60), "river")
    assert t == "Good"                                  # dawn plus but not peak -> no up
    t, _, i = C.tier_for(SPECIES, "good", cond("dawn", "pre_front_falling"), feats(70), "river")
    assert t == "Prime" and i["up"]                     # peak + 2 plus -> one up
    t, _, _ = C.tier_for(SPECIES, "prime", cond("dawn", "pre_front_falling"), feats(70, "rising"), "river")
    assert t == "Prime"                                 # capped
    t, _, _ = C.tier_for(SPECIES, "fair", cond("day", "post_front_high_rising"), feats(50, "falling", "likely_muddy"), "river")
    assert t == "Poor"                                  # floor
    t, r, _ = C.tier_for(SPECIES, "good", cond("dawn"), feats(None), "river")
    assert t == "Good" and any(x["label"] == "not_found" for x in r)


def test_tier_tide_only_on_tidal():
    t, _, _ = C.tier_for(SPECIES, "good", cond("dawn", tide="slack"), feats(60), "pier")
    assert t == "Fair"
    t, _, _ = C.tier_for(SPECIES, "good", cond("dawn", tide="slack"), feats(60), "river")
    assert t == "Good"


def test_overcast_cancels_day_minus():
    t, _, _ = C.tier_for(SPECIES, "good", cond("day", overcast=True), feats(60), "river")
    assert t == "Good"


def test_confidence():
    f = feats(60)
    assert C.confidence_for(f, "river", True)[0] == "high"
    assert C.confidence_for(f, "river", False)[0] == "medium"
    assert C.confidence_for(feats(None), "river", True)[0] == "medium"     # drops one
    f2 = feats(None)
    f2["flow"]["current"]["label"] = "not_found"
    assert C.confidence_for(f2, "river", False)[0] == "low"
    bay = {"water_temp": {"label": "measured"}, "flow": {}, "tide": {"label": "forecast"}}
    assert C.confidence_for(bay, "pier", True)[0] == "high"


def test_trips_for():
    tt = {"quick": {"max_drive_min": 35}, "half": {"max_drive_min": 95}, "full": {"max_drive_min": 190}}
    assert C.trips_for(30, tt) == ["quick", "half", "full"]
    assert C.trips_for(95, tt) == ["half", "full"]
    assert C.trips_for(200, tt) == []


def _cand(tier, conf, flow_vs=None, gust=None, start=None):
    start = start or NOW + timedelta(hours=1)
    c = {"flow": {"vs_ceiling": flow_vs}} if flow_vs else {}
    c["wind"] = {"max_gust_mph": gust}
    return {"tier": tier, "confidence": conf, "_w": {"conditions": c, "start": start}}


def test_verdict_logic():
    assert K.verdict_for(_cand("Prime", "high"), 30)[0] == "GO"
    assert K.verdict_for(_cand("Good", "medium"), 30)[0] == "GO"
    assert K.verdict_for(_cand("Good", "low"), 30) == ("GO IF", "low_conf")
    assert K.verdict_for(_cand("Fair", "high", flow_vs="near"), 30) == ("GO IF", "flow_near")
    assert K.verdict_for(_cand("Fair", "high", gust=26), 30) == ("GO IF", "gust_near")
    assert K.verdict_for(_cand("Fair", "high", gust=20), 30)[0] == "SKIP"
    assert K.verdict_for(_cand("Poor", "high"), 30)[0] == "SKIP"
    assert K.verdict_for(None)[0] == "SKIP"


def test_window_matches():
    from engine.util import ET
    d = lambda s: {"date": s.date().isoformat(), "start": s, "end": s + timedelta(hours=3)}
    assert K.window_matches("next3h", d(NOW + timedelta(hours=1)), NOW)
    assert not K.window_matches("next3h", d(NOW + timedelta(hours=4)), NOW)
    assert K.window_matches("tomorrow_am", d(NOW.replace(day=15, hour=7)), NOW)
    assert not K.window_matches("tomorrow_am", d(NOW.replace(day=15, hour=13)), NOW)
    assert K.window_matches("weekend", d(NOW.replace(day=17, hour=7)), NOW)       # Sat
    assert not K.window_matches("weekend", d(NOW.replace(day=16, hour=7)), NOW)   # Fri
    assert not K.window_matches("weekend", d(NOW.replace(day=24, hour=7)), NOW)   # next week
