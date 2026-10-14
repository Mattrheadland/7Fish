from datetime import timedelta

from conftest import NOW

from engine import features as F
from engine.util import drive_minutes


def hpa_series(fn, hours=72):
    """fn(h_before_now) -> hPa. Hourly series ending at NOW."""
    return [(NOW - timedelta(hours=h), fn(h)) for h in range(hours, -1, -1)]


INHG = 1 / 0.0295299830714  # hPa per inHg


def test_pressure_rising_falling_steady():
    cfg = {}
    rising = F.pressure_features(hpa_series(lambda h: 1015 - h * (0.08 * INHG / 24)), NOW, cfg)
    assert rising["class"] == "rising"
    falling = F.pressure_features(hpa_series(lambda h: 1015 + h * (0.08 * INHG / 24)), NOW, cfg)
    assert falling["class"] == "falling" and falling["front"] == "steady"
    steady = F.pressure_features(hpa_series(lambda h: 1015.0), NOW, cfg)
    assert steady["class"] == "steady" and steady["front"] == "steady"


def test_pressure_fronts():
    fast_fall = F.pressure_features(hpa_series(lambda h: 1010 + h * (0.15 * INHG / 24)), NOW, {})
    assert fast_fall["front"] == "pre_front_falling"
    # fell 48-24h ago, then rising fast in the last 24h
    def v(h):
        if h >= 24:
            return 1000 + (h - 24) * (0.12 * INHG / 24)   # falling toward h=24
        return 1000 + (24 - h) * (0.15 * INHG / 24)       # rising since
    post = F.pressure_features(hpa_series(v), NOW, {})
    assert post["class"] == "rising" and post["front"] == "post_front_high_rising"
    # rising fast but no prior fall in record -> not post-front
    steady_rise = F.pressure_features(hpa_series(lambda h: 1020 - h * (0.12 * INHG / 24) if h < 24 else 1020 - 24 * (0.12 * INHG / 24)), NOW, {})
    assert steady_rise["class"] == "rising"


def test_pressure_missing():
    assert F.pressure_features([], NOW, {})["class"] == "unknown"
    only_now = F.pressure_features([(NOW, 1015.0)], NOW, {})
    assert only_now["class"] == "unknown" and only_now["now_inhg"] == 29.97


def test_flow_trend_and_ceiling():
    rising = [(NOW - timedelta(hours=h), 1000 + (72 - h) * 5) for h in range(72, -1, -1)]
    assert F.flow_trend(rising, NOW) == "rising"
    assert F.flow_trend([(t, 1000) for t, _ in rising], NOW) == "steady"
    assert F.flow_trend([(t, 2000 - (72 - (NOW - t).total_seconds() / 3600) * 10) for t, _ in rising], NOW) == "falling"
    assert F.flow_trend([], NOW) == "unknown"
    assert F.vs_ceiling(5000, 4000) == "over"
    assert F.vs_ceiling(3500, 4000) == "near"      # >= 85%
    assert F.vs_ceiling(3399, 4000) == "under"
    assert F.vs_ceiling(None, 4000) == "unknown"
    assert F.vs_ceiling(3000, None) == "unknown"


def test_clarity_proxy():
    assert F.clarity_proxy(0.8, 0.0, "steady")["v"] == "likely_muddy"
    assert F.clarity_proxy(0.2, 0.35, "rising")["v"] == "likely_muddy"
    assert F.clarity_proxy(0.05, -0.05, "falling")["v"] == "likely_clear"
    assert F.clarity_proxy(0.05, 0.2, "rising")["v"] == "unknown"
    assert F.clarity_proxy(None, None, "unknown")["v"] == "unknown"
    # buoy turbidity overrides
    t = F.clarity_proxy(1.5, 0.0, "n/a", turbidity=4)
    assert t["v"] == "likely_clear" and t["label"] == "measured"
    assert F.clarity_proxy(0.0, 0.0, "n/a", turbidity=40)["v"] == "likely_muddy"


def test_tide_stage():
    hilo = [{"t": NOW, "type": "L", "v": 0.2}, {"t": NOW + timedelta(hours=6), "type": "H", "v": 1.6},
            {"t": NOW + timedelta(hours=12, minutes=20), "type": "L", "v": 0.3}]
    assert F.tide_stage(hilo, NOW + timedelta(minutes=30)) == "slack"
    assert F.tide_stage(hilo, NOW + timedelta(hours=3)) == "incoming"
    assert F.tide_stage(hilo, NOW + timedelta(hours=9)) == "outgoing"
    assert F.tide_stage(hilo, NOW + timedelta(hours=5, minutes=20)) == "slack"
    assert F.tide_stage(hilo, NOW - timedelta(hours=3)) == "outgoing"   # before first: next is L
    assert F.tide_stage([], NOW) == "unknown"
    w = F.window_tide(hilo, NOW + timedelta(hours=1), NOW + timedelta(hours=5))
    assert w["dominant"] == "incoming" and w["turns"] == []


def test_wind_onshore_offshore_cross():
    # angler faces east (90): wind FROM the east blows toward the angler -> onshore
    assert F.wind_relation(90, 90) == "onshore"
    assert F.wind_relation(140, 90) == "onshore"       # within 60
    assert F.wind_relation(270, 90) == "offshore"
    assert F.wind_relation(0, 90) == "cross"
    assert F.wind_relation(350, 20) == "onshore"       # wraps north
    assert F.wind_relation(None, 90) == "unknown"
    assert F.wind_relation(90, None) == "unknown"


def test_water_temp_pick_rules():
    c = [{"v": 60.0, "at": NOW - timedelta(hours=1), "src": "USGS far", "dist_mi": 30},
         {"v": 58.0, "at": NOW - timedelta(hours=48), "src": "USGS stale", "dist_mi": 1}]
    assert F.pick_water_temp(c, NOW)["label"] == "not_found"
    c.append({"v": 61.0, "at": NOW - timedelta(hours=2), "src": "CO-OPS ok", "dist_mi": 10})
    got = F.pick_water_temp(c, NOW)
    assert got["v"] == 61.0 and got["label"] == "measured" and got["src"] == "CO-OPS ok"


def test_open_meteo_never_water_temp(http):
    """Build a spot with only Open-Meteo + NWS: water temp must be not_found."""
    from engine.collect import nws, openmeteo
    spot = {"id": "x", "lat": 39.38, "lon": -77.4, "water_type": "river", "stations": {}}
    data = {"nws": nws.fetch(http, 39.38, -77.4), "om": openmeteo.fetch(http, 39.38, -77.4)}
    res = F.build_spot(spot, data, NOW, {})
    assert res["features"]["water_temp"]["label"] == "not_found"
    assert res["features"]["water_temp"]["v"] is None


def test_windows_skip_ended_and_night_rules():
    from engine.collect import astro
    days = [astro.day(39.4, -77.4, (NOW + timedelta(days=i)).date()) for i in range(3)]
    later = NOW.replace(hour=14)
    wins = F.make_windows(days, later, "prohibited")
    ids = [w["id"] for w in wins]
    assert "2026-10-14|dawn" not in ids and "2026-10-14|day" in ids
    assert not any(w["kind"] == "night" for w in wins)
    assert any(w["kind"] == "night" for w in F.make_windows(days, later, "allowed"))
    d0 = days[0]
    assert d0["civil_dawn"] < d0["sunrise"] < d0["sunset"] < d0["civil_dusk"]
    assert 6 <= d0["sunrise"].hour <= 7          # mid-October Frederick
    assert d0["moon_phase"] and 0 <= d0["moon_illum_pct"] <= 100


def test_drive_minutes():
    assert drive_minutes(39.4143, -77.4105) == 0
    # ~57 mi straight line to Annapolis -> 57 * 1.25 / 48 * 60 ≈ 89 -> 90
    m = drive_minutes(38.98, -76.49)
    assert m == 90
