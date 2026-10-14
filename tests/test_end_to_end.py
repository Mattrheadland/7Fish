"""Full offline run over tests/fixtures/{api,knowledge}; never touches the real knowledge files."""
import json

import pytest
from conftest import API, KNOW, NOW

from engine import run as R

LABELS = {"measured", "forecast", "modeled", "report", "reasoning", "not_found"}


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    out = tmp_path_factory.mktemp("data")
    res = R.run(knowledge_dir=KNOW, out_dir=out, offline=str(API), now=NOW)
    return res, out


def test_files_written(result):
    res, out = result
    latest = json.loads((out / "latest.json").read_text())
    assert (out / "history" / "2026-10-14.json").exists()
    log = json.loads((out / "run_log.json").read_text())
    assert latest["version"] == 1 and latest["origin"]["lat"] == 39.4143
    assert set(log["sources"]) >= {"nws", "openmeteo", "usgs", "nwps", "coops", "cbibs", "astro", "dnr"}
    assert "duration_s" in log and log["generated_at"]
    assert res["bytes"] < 1_500_000


def test_spots_and_ruled_out(result):
    res, _ = result
    L = res["latest"]
    assert set(L["spots"]) == {"river-a", "bay-b"}
    assert L["spots_listed"]["ruled-c"]["why"] == "ruled out"
    assert all(c["spot"] != "ruled-c" for c in L["candidates"])
    assert any("broken.yaml" in n for n in res["run_log"]["notes"])


def test_gated_windows_excluded(result):
    res, _ = result
    L = res["latest"]
    ids = {(c["spot"], c["window"]) for c in L["candidates"]}
    # thunder on Oct 16 afternoon, closure for striped bass Oct 16, river-a has no night
    assert ("river-a", "2026-10-16|day") not in ids
    assert ("bay-b", "2026-10-16|dawn") not in ids
    assert not any(c["window"].endswith("night") and c["spot"] == "river-a" for c in L["candidates"])
    river = L["spots"]["river-a"]
    thunder = [w for w in river["windows"] if w["id"] == "2026-10-16|day"][0]
    assert any(g["name"] == "thunder" and not g["pass"] for g in thunder["gates"])


def test_no_numeric_scores_and_words_only(result):
    res, _ = result
    L = res["latest"]
    for c in L["candidates"]:
        assert c["tier"] in ("Prime", "Good", "Fair", "Poor")
        assert c["confidence"] in ("high", "medium", "low")
        assert not any(k in c for k in ("score", "rank", "probability"))
    text = json.dumps(L).lower()
    assert '"score"' not in text and "probability" not in text


def test_cards_cover_every_combo_and_match_schema(result):
    res, _ = result
    cards = res["latest"]["cards"]
    assert len(cards) == 18
    schema = json.loads((R.ROOT / "engine" / "schema" / "card.schema.json").read_text())
    cand_windows = {(c["spot"], c["species"], c["window"]) for c in res["latest"]["candidates"]}
    for key, card in cards.items():
        when, trip, luca = key.split("|")
        _validate(card, schema)
        assert card["source"] == "engine"
        if card["play"]:
            p = card["play"]
            assert (p["spot_id"], p["species_key"], p["window_id"]) in cand_windows
            assert "2026" in p["window_text"] and "ET" in p["window_text"]
            if luca == "true":
                assert p["spot_id"] == "river-a"     # only luca_ok spot + kid-friendly species
        for d in card["details"].get("drivers", []):
            assert d["label"] in LABELS
        if card["verdict"] == "GO IF":
            assert card["condition"]
        if card["verdict"] == "SKIP":
            assert card["play"] is None and card["details"]["skip"]["reason"]


def test_quick_trip_respects_drive(result):
    res, _ = result
    for key, card in res["latest"]["cards"].items():
        if "|quick|" in key and card["play"]:
            assert card["details"]["time"]["drive_min"] <= 35


def test_water_temp_labels(result):
    res, _ = result
    for s in res["latest"]["spots"].values():
        wt = s["features"]["water_temp"]
        assert wt["label"] in ("measured", "not_found")
        assert "Open-Meteo" not in str(wt.get("src"))


def test_dnr_lean(result):
    res, _ = result
    d = res["latest"]["dnr"]
    assert set(d) == {"date", "link", "title", "by_species"}
    for sents in d["by_species"].values():
        assert len(sents) <= 3 and all(len(s) <= 240 for s in sents)


def test_shape_logged(result):
    res, _ = result
    assert res["run_log"]["sources"]["usgs"]["shape"]["feature_property_keys"]


def test_survives_total_source_failure(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    res = R.run(knowledge_dir=KNOW, out_dir=tmp_path / "o", offline=str(empty), now=NOW)
    L = res["latest"]
    assert not L["sources_ok"]["nws"] and not L["sources_ok"]["usgs"]
    for s in L["spots"].values():
        assert s["features"]["water_temp"]["label"] == "not_found"
    assert len(L["cards"]) == 18
    for c in L["candidates"]:
        assert c["confidence"] in ("low", "medium")


def test_main_cli(tmp_path, capsys):
    rc = R.main(["--offline", str(API), "--knowledge", str(KNOW), "--out", str(tmp_path), "--now", "2026-10-14T05:00-04:00"])
    assert rc == 0 and (tmp_path / "latest.json").exists()
    assert "candidates" in capsys.readouterr().out


# ---------------------------------------------------------------- tiny JSON-schema checker
def _validate(obj, schema, path="card"):
    t = schema.get("type")
    if "enum" in schema:
        assert obj in schema["enum"], f"{path}: {obj!r} not in {schema['enum']}"
    if t:
        types = t if isinstance(t, list) else [t]
        ok = any(_is(obj, ty) for ty in types)
        assert ok, f"{path}: {type(obj).__name__} not {types}"
    if obj is None:
        return
    if isinstance(obj, str) and "maxLength" in schema:
        assert len(obj) <= schema["maxLength"], path
    if isinstance(obj, dict):
        for r in schema.get("required", []):
            assert r in obj, f"{path}: missing {r}"
        for k, sub in (schema.get("properties") or {}).items():
            if k in obj:
                _validate(obj[k], sub, f"{path}.{k}")
    if isinstance(obj, list):
        if "maxItems" in schema:
            assert len(obj) <= schema["maxItems"], path
        for i, it in enumerate(obj):
            _validate(it, schema.get("items", {}), f"{path}[{i}]")


def _is(o, t):
    return {"object": isinstance(o, dict), "array": isinstance(o, list), "string": isinstance(o, str),
            "number": isinstance(o, (int, float)) and not isinstance(o, bool), "null": o is None,
            "boolean": isinstance(o, bool)}.get(t, True)
