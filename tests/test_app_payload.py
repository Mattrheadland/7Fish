from engine import app_payload


def test_split_keeps_every_part_under_doc_limit():
    big_reason = {"text": "x" * 400, "label": "reasoning"}
    cands = [{"spot": "s", "species": "k", "window": f"2026-10-{15 + i % 5}|dawn", "reasons": [big_reason] * 3}
             for i in range(600)]
    payload = {"generated_at": "g", "cands": cands, "spots": {}, "cards": {}, "kn": {}}
    parts = app_payload.split(payload)
    assert set(parts) == {"meta", "spots", "cands", "cards"}
    for p in parts.values():
        assert p["_bytes"] <= app_payload.DOC_LIMIT
        assert p["generated_at"] == "g"
    days = {r["window"].split("|")[0] for r in parts["cands"]["cands"]}
    assert len(days) == 5  # trimming keeps every day represented
