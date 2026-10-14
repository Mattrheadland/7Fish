from datetime import date

from engine.knowledge import Knowledge, _in_mmdd, is_ruled_out, norm_status


def test_loads_and_tolerates(kn):
    assert set(kn.species) == {"test-catfish", "striped-bass"}
    assert "broken" not in kn.spots and "ruled-c" in kn.spots
    assert set(kn.active_spots()) == {"river-a", "bay-b"}
    assert any("broken.yaml" in p for p in kn.problems)
    assert kn.species["test-catfish"]["unknown_future_key"]   # unknown keys kept, ignored
    assert kn.gates["wind"]["default_gust_limit_mph"] == 30
    assert kn.profile["trip_types"]["quick"]["max_drive_min"] == 35


def test_empty_dir(tmp_path):
    k = Knowledge(tmp_path)
    assert k.species == {} and k.spots == {} and k.regs == {}
    assert k.gates["flow"]["near_fraction"] == 0.85
    assert k.profile["origin"]["lat"] == 39.4143


def test_status_words():
    assert norm_status("not_verified") == "not verified"
    assert norm_status("verified") == "verified"
    assert norm_status("ruled-out") == "ruled out"
    assert norm_status(None) == "not verified"
    assert is_ruled_out("ruled_out")


def test_mmdd_ranges():
    assert _in_mmdd(date(2026, 4, 1), "04-01", "05-15")
    assert _in_mmdd(date(2026, 5, 15), "04-01", "05-15")
    assert not _in_mmdd(date(2026, 5, 16), "04-01", "05-15")
    assert _in_mmdd(date(2026, 1, 5), "12-20", "03-31")      # wraps year end
    assert not _in_mmdd(date(2026, 6, 1), "12-20", "03-31")
    assert not _in_mmdd(date(2026, 6, 1), None, "bad")


def test_real_knowledge_files_parse():
    """Smoke: whatever is in the real knowledge/ dir right now must load without raising."""
    from engine.run import ROOT
    k = Knowledge(ROOT / "knowledge")
    assert isinstance(k.species, dict) and isinstance(k.spots, dict)
    assert k.gates["alerts"]["all_spots"]
