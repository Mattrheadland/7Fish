"""Each collector against a synthetic fixture shaped like the public API docs."""
import json

from conftest import API, NOW

from engine.collect import cbibs, coops, dnr, nwps, nws, openmeteo, usgs
from engine.http import Http, RunLog, describe_shape


def test_nws_hourly_gusts_alerts(http):
    out = nws.fetch(http, 39.3876, -77.3708)
    assert out["ok_hourly"] and out["ok_alerts"]
    h = out["hourly"][0]
    assert h["temp_f"] == 52
    assert h["wind_mph"] == 10          # "5 to 10 mph" -> max
    assert h["wind_dir_deg"] == 270     # W
    assert round(h["gust_mph"]) == 15   # 24.1 km/h from gridpoint windGust
    assert out["alerts"][0]["event"] == "Heat Advisory"
    assert http.log.sources["nws"]["shape_points"]["property_keys"]


def test_nws_wind_formats():
    assert nws._wind_mph("10 mph") == 10
    assert nws._wind_mph({"unitCode": "wmoUnit:km_h-1", "value": 16.09}) == 16.09 * 0.621371
    assert nws._wind_mph(None) is None
    assert nws._gust_from_text("West wind, with gusts as high as 25 mph.") == 25


def test_openmeteo(http):
    out = openmeteo.fetch(http, 39.38, -77.4)
    assert out["ok"]
    p = out["series"]["pressure_msl"]
    assert len(p) == 168 and p[0][0].tzinfo is not None
    assert "soil_temperature_0cm" not in out["series"] and "surface_temperature" not in out["series"]


def test_usgs_ogc(http):
    out = usgs.fetch(http, "01643000")
    assert out["ok"]
    assert out["discharge"][-1][1] == 1700 - 72 * 3
    assert 59 < out["water_temp"][-1][1] < 62      # °C converted to °F
    assert out["units"]["water_temp"] == "degF"
    assert out["lat"] == 39.3876
    shape = http.log.sources["usgs"]["shape"]
    assert "value" in shape["feature_property_keys"] and "time" in shape["feature_property_keys"]


def test_usgs_parser_tolerates_renamed_and_missing_fields():
    data = {"features": [
        {"properties": {"datetime": "2026-10-14T09:00:00Z", "result": "12.5", "parameter_code": "00010"}},
        {"properties": {"time": "2026-10-14T10:00:00Z", "value": None}},
        {"properties": {"time": "2026-10-14T11:00:00Z", "value": "3.0", "parameter_code": "00065"}},
        {"nothing": True},
    ]}
    s, _ = usgs.parse_features(data, "00010")
    assert len(s) == 1 and s[0][1] == 12.5
    assert usgs.parse_features(None, "00010") == ([], None)


def test_usgs_url_is_new_api_only():
    assert usgs.URL.startswith("https://api.waterdata.usgs.gov/ogcapi/")
    import pathlib
    for p in pathlib.Path(usgs.__file__).parent.parent.rglob("*.py"):
        txt = p.read_text()
        assert "waterservices.usgs.gov/nwis" not in txt, p


def test_nwps(http):
    out = nwps.fetch(http, "TEST1")
    assert out["ok"]
    assert out["categories"]["action"]["stage"] == 10.0
    assert out["categories"]["action"]["flow"] is None        # -9999 -> missing
    assert out["observed"]["flow"][-1][1] == 1490.0            # kcfs -> cfs
    assert out["forecast"]["stage"]
    assert nwps.category_for(16, out["categories"]) == "minor"
    assert nwps.category_for(3, out["categories"]) == "none"
    assert nwps.category_for(None, out["categories"]) == "unknown"


def test_coops(http):
    out = coops.fetch(http, "8575512", NOW)
    assert out["ok"]
    assert out["hilo"][0]["type"] in ("H", "L")
    assert out["water_temp"][-1][1] == 64.2
    assert out["wind"][0]["speed_kt"] == 6.8


def test_coops_error_payload(tmp_path):
    d = tmp_path / "coops"
    d.mkdir()
    (d / "predictions.json").write_text(json.dumps({"error": {"message": "No Predictions data was found."}}))
    h = Http(RunLog(), offline_dir=str(tmp_path))
    out = coops.fetch(h, "0000000", NOW)
    assert out["hilo"] == [] and not out["ok"]
    assert any("No Predictions" in e for e in h.log.sources["coops"]["errors"])


def test_cbibs_with_fixture(http):
    out = cbibs.fetch(http, "AN")
    v = out["values"]
    assert round(v["water_temp"]["v"], 1) == round(17.9 * 9 / 5 + 32, 1)
    assert v["turbidity"]["v"] == 4.1          # string value parsed
    assert "air_temp" not in v


def test_cbibs_skips_without_key(monkeypatch):
    monkeypatch.delenv("CBIBS_KEY", raising=False)
    h = Http(RunLog())  # live mode, but must not call out
    out = cbibs.fetch(h, "AN")
    assert out["skipped"] and h.log.sources["cbibs"]["n_calls"] == 0


def test_dnr_short_sentences_only(http):
    species = {"striped-bass": {"name": "Striped bass"}, "test-catfish": {"name": "Test catfish"}}
    out = dnr.fetch(http, species)
    assert out["date"] == "2026-10-08"
    assert out["title"] == "Maryland Fishing Report – October 8"
    sb = out["by_species"]["striped-bass"]
    assert 1 <= len(sb) <= 3 and all(len(s) <= 240 for s in sb)
    assert any("Rockfish" in s for s in sb)       # alias match
    assert "content" not in out and "text" not in out
    assert "smallmouth-bass" not in out["by_species"]   # not in species list


def test_dnr_extract_caps():
    text = " ".join(f"Striped bass sentence number {i} " + "x" * 300 + "." for i in range(6))
    got = dnr.extract(text, {"striped-bass": ["striped bass"]})["striped-bass"]
    assert len(got) == 3 and all(len(s) <= 240 for s in got)


def test_missing_fixture_is_not_found_not_crash(tmp_path):
    h = Http(RunLog(), offline_dir=str(tmp_path))
    out = nws.fetch(h, 39.0, -77.0)
    assert out["hourly"] == [] and out["alerts"] == []
    assert h.log.sources["nws"]["ok"] is False
    assert usgs.fetch(h, "01638500")["ok"] is False
    assert nwps.fetch(h, "X")["ok"] is False
    assert dnr.fetch(h, {})["date"] is None


def test_describe_shape():
    s = describe_shape({"a": 1, "features": [{"properties": {"x": 1, "y": 2}}]})
    assert s["keys"] == ["a", "features"] and s["feature_property_keys"] == ["x", "y"]
    assert describe_shape([{"k": 1}])["item_keys"] == ["k"]


def test_http_user_agent():
    from engine.http import USER_AGENT
    h = Http(RunLog())
    assert h.session.headers["User-Agent"] == USER_AGENT == "7Fish (github.com/Mattrheadland/7Fish)"
