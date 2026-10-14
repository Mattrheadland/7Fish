"""Serialize the run: data/latest.json, data/history/YYYY-MM-DD.json, data/run_log.json.

Everything is converted to JSON-safe primitives here: datetimes -> ISO ET strings,
floats rounded, private keys (leading underscore) dropped.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from .util import ET

MAX_BYTES = 1_500_000


def clean(o, nd=2):
    if isinstance(o, datetime):
        return o.astimezone(ET).isoformat(timespec="minutes")
    if isinstance(o, date):
        return o.isoformat()
    if isinstance(o, float):
        return round(o, nd)
    if isinstance(o, dict):
        return {str(k): clean(v, 4 if k in ("lat", "lon") else nd) for k, v in o.items()
                if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [clean(v, nd) for v in o]
    return o


def candidate_out(c: dict) -> dict:
    return clean({k: v for k, v in c.items() if not k.startswith("_")})


def spot_out(kn, sid, res) -> dict:
    spot = kn.spots[sid]
    wins = []
    for w in res["windows"]:
        wins.append({
            "id": w["id"], "kind": w["kind"], "start": w["start"], "end": w["end"],
            "clip": w.get("clip"),
            "gates": w["gates"],
            "species_gates": w.get("species_gates", {}),
            "conditions": w.get("conditions", {}),
        })
    alerts = [{"event": a.get("event"), "start": a.get("start"), "end": a.get("end"), "headline": a.get("headline")}
              for a in res.get("alerts") or []]
    return clean({"name": spot.get("name"), "status": spot.get("status"), "region": spot.get("region"),
                  "water_type": spot.get("water_type"), "lat": spot.get("lat"), "lon": spot.get("lon"),
                  "features": res["features"], "alerts": alerts, "windows": wins})


def listed_only(kn, active_ids) -> dict:
    """Spots that are listed but not forecast (ruled out or missing coordinates)."""
    out = {}
    for sid, s in kn.spots.items():
        if sid in active_ids:
            continue
        out[sid] = {"name": s.get("name"), "status": s.get("status"), "region": s.get("region"),
                    "forecast": False,
                    "why": "ruled out" if str(s.get("status", "")).lower().replace("_", "-") in ("ruled-out", "ruled out") else "no coordinates"}
    return out


def write(out_dir: str | Path, latest: dict, run_log: dict, now: datetime) -> dict:
    out_dir = Path(out_dir)
    (out_dir / "history").mkdir(parents=True, exist_ok=True)
    payload = clean(latest)
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    if len(text.encode()) > MAX_BYTES:
        # shed bulk: hourly series first, then window conditions detail
        for s in payload.get("spots", {}).values():
            s.get("features", {}).pop("hourly", None)
        text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        run_log.setdefault("notes", []).append("latest.json over size budget; hourly series dropped")
    (out_dir / "latest.json").write_text(text)
    day = now.astimezone(ET).date().isoformat()
    (out_dir / "history" / f"{day}.json").write_text(text)
    run_log["latest_bytes"] = len(text.encode())
    (out_dir / "run_log.json").write_text(json.dumps(clean(run_log), indent=1, ensure_ascii=False))
    return {"bytes": len(text.encode())}
