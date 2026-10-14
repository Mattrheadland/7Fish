from datetime import timedelta

from conftest import NOW

from engine import gates as G
from engine.knowledge import DEFAULT_GATES


def win(kind="dawn", date="2026-10-15", start_h=7, end_h=10):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    d = datetime.fromisoformat(date).replace(tzinfo=et)
    return {"id": f"{date}|{kind}", "date": date, "kind": kind,
            "start": d.replace(hour=start_h), "end": d.replace(hour=end_h % 24) if end_h < 24 else d.replace(hour=23, minute=59),
            "sunrise": d.replace(hour=7, minute=10), "sunset": d.replace(hour=18, minute=30)}


def test_alert_gate_types_and_overlap():
    w = win()
    sev = [{"event": "Severe Thunderstorm Warning", "start": w["start"] + timedelta(hours=1), "end": w["end"] + timedelta(hours=1)}]
    assert not G.alert_gate(sev, w, "river", DEFAULT_GATES)["pass"]
    before = [{"event": "Severe Thunderstorm Warning", "start": w["start"] - timedelta(hours=5), "end": w["start"] - timedelta(hours=1)}]
    assert G.alert_gate(before, w, "river", DEFAULT_GATES)["pass"]
    heat = [{"event": "Heat Advisory", "start": w["start"], "end": w["end"]}]
    assert G.alert_gate(heat, w, "river", DEFAULT_GATES)["pass"]
    sca = [{"event": "Small Craft Advisory", "start": None, "end": None}]
    assert G.alert_gate(sca, w, "river", DEFAULT_GATES)["pass"]
    assert not G.alert_gate(sca, w, "pier", DEFAULT_GATES)["pass"]
    assert not G.alert_gate(sca, w, "inlet", DEFAULT_GATES)["pass"]
    unchecked = G.alert_gate([], w, "river", DEFAULT_GATES, checked=False)
    assert unchecked["pass"] and "not checked" in unchecked["reason"]


def test_alert_gate_respects_yaml(kn):
    w = win()
    sca = [{"event": "Small Craft Advisory", "start": w["start"], "end": w["end"]}]
    # the real gates.yaml lists SCA under not_gates AND under water_types.pier; pier must still gate
    assert not G.alert_gate(sca, w, "pier", kn.gates)["pass"]
    assert G.alert_gate(sca, w, "river", kn.gates)["pass"]


def test_thunder_gate():
    assert not G.thunder_gate(["Chance Showers And Thunderstorms"], DEFAULT_GATES)["pass"]
    assert not G.thunder_gate(["Slight Chance T-storms"], DEFAULT_GATES)["pass"]
    assert G.thunder_gate(["Sunny", "Mostly Clear"], DEFAULT_GATES)["pass"]


def test_gust_gate():
    assert not G.gust_gate(31, 30)["pass"]
    assert G.gust_gate(30, 30)["pass"]
    assert G.gust_gate(None, 30)["pass"]


def test_flow_gate():
    assert not G.flow_gate({"vs_ceiling": "over", "v": 5000, "unit": "cfs", "label": "measured"}, "matt", DEFAULT_GATES)["pass"]
    assert G.flow_gate({"vs_ceiling": "near", "nwps_category": "none"}, "matt", DEFAULT_GATES)["pass"]
    # no ceiling: NWPS action or above fails
    assert not G.flow_gate({"vs_ceiling": "unknown", "nwps_category": "action"}, "ask_matt", DEFAULT_GATES)["pass"]
    assert G.flow_gate({"vs_ceiling": "unknown", "nwps_category": "none"}, "ask_matt", DEFAULT_GATES)["pass"]
    # with a ceiling set, action alone doesn't fail, minor does
    assert G.flow_gate({"vs_ceiling": "under", "nwps_category": "action"}, "matt", DEFAULT_GATES)["pass"]
    assert not G.flow_gate({"vs_ceiling": "under", "nwps_category": "minor"}, "matt", DEFAULT_GATES)["pass"]
    assert G.flow_gate(None, None, DEFAULT_GATES)["pass"]


def test_hours_gate():
    sunrise_sunset = {"access": {"hours": {"open": "sunrise", "close": "sunset"}, "after_dark": "prohibited"}}
    dawn = win("dawn", start_h=6, end_h=10)
    r = G.hours_gate(sunrise_sunset, dawn)
    assert r["pass"] and "clipped" in r["reason"] and dawn["clip"]["start"] == dawn["sunrise"]
    night = win("night", start_h=19, end_h=24)
    assert not G.hours_gate(sunrise_sunset, night)["pass"]
    # hours not found -> daylight ok, night fails even if after_dark allowed
    nf = {"access": {"hours": {"open": "not found", "close": "not found"}, "after_dark": "allowed"}}
    assert G.hours_gate(nf, win("day", start_h=10, end_h=16))["pass"]
    assert not G.hours_gate(nf, win("night", start_h=19, end_h=24))["pass"]
    # missing access block entirely
    assert G.hours_gate({}, win("dusk", start_h=16, end_h=19))["pass"]
    # fixed clock outside window
    fixed = {"access": {"hours": {"open": "08:00", "close": "17:00"}}}
    assert not G.hours_gate(fixed, win("dusk", start_h=17, end_h=19))["pass"]
    assert G.hours_gate({"access": {"hours": {"open": "24h", "close": "24h"}, "after_dark": "allowed"}},
                        win("night", start_h=19, end_h=24))["pass"]


def test_status_gate():
    assert not G.status_gate({"status": "ruled-out"})["pass"]
    assert not G.status_gate({"status": "ruled_out"})["pass"]
    assert G.status_gate({"status": "active"})["pass"]


def test_species_gates(kn):
    closed = G.species_window_gates(kn, "striped-bass", "middle-bay", win(date="2026-10-16"))
    assert not G.all_pass(closed) and "closed" in closed[0]["reason"]
    assert G.all_pass(G.species_window_gates(kn, "striped-bass", "middle-bay", win(date="2026-10-15")))
    absent = G.species_window_gates(kn, "test-catfish", "frederick-rivers", win(date="2026-12-15"))
    assert not absent[1]["pass"]
    no_region = G.species_window_gates(kn, "test-catfish", "md-coast", win())
    assert not no_region[1]["pass"]
