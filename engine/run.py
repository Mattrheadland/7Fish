"""Entry point: python -m engine.run [--offline FIXTURE_DIR] [--knowledge DIR] [--out DIR] [--now ISO]

Never crashes on a source failure. Exit code is non-zero only for a programming error
outside the collectors (and even then run_log.json is written first).
"""
from __future__ import annotations

import argparse
import sys
import time as _time
import traceback
from datetime import datetime
from pathlib import Path

from . import candidates as cand_mod
from . import cards as cards_mod
from . import features, gates, output
from .collect import cbibs, coops, dnr, nwps, nws, openmeteo, usgs
from .http import Http, RunLog
from .knowledge import Knowledge
from .util import ET, UTC, parse_time

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ["nws", "openmeteo", "usgs", "nwps", "coops", "cbibs", "astro", "dnr"]


def _sid(st: dict | None, key="id"):
    if not isinstance(st, dict):
        return None
    v = st.get(key)
    if v in (None, "", "null", "not found") and key != "id":
        v = st.get("id")
    if v in (None, "", "null", "not found"):
        return None
    return str(v)


def collect_spot(http, spot, now, cache) -> dict:
    lat, lon = spot["lat"], spot["lon"]
    st = spot.get("stations") or {}
    data = {}
    k = ("nws", round(lat, 3), round(lon, 3))
    if k not in cache:
        cache[k] = nws.fetch(http, lat, lon)
    data["nws"] = cache[k]
    k = ("om", round(lat, 2), round(lon, 2))
    if k not in cache:
        cache[k] = openmeteo.fetch(http, lat, lon)
    data["om"] = cache[k]
    for name, mod, key in (("usgs", usgs, "id"), ("nwps", nwps, "lid"), ("coops", coops, "id"), ("cbibs", cbibs, "id")):
        sid = _sid(st.get(name), key)
        if not sid:
            data[name] = None
            continue
        ck = (name, sid)
        if ck not in cache:
            if name == "coops":
                cache[ck] = mod.fetch(http, sid, now)
            else:
                cache[ck] = mod.fetch(http, sid)
        data[name] = cache[ck]
    return data


def run(knowledge_dir=None, out_dir=None, offline=None, record=None, now=None) -> dict:
    t0 = _time.time()
    log = RunLog()
    now = now or datetime.now(UTC)
    now = now.astimezone(ET)
    knowledge_dir = Path(knowledge_dir or ROOT / "knowledge")
    out_dir = Path(out_dir or ROOT / "data")
    http = Http(log, offline_dir=offline, record_dir=record, sleep_between_retries=0 if offline else 2.0)
    kn = Knowledge(knowledge_dir, log)
    log.knowledge = {"species": sorted(kn.species), "spots": sorted(kn.spots),
                     "active_spots": sorted(kn.active_spots()), "regs_loaded": bool(kn.regs),
                     "problems": kn.problems[:30]}
    for s in SOURCES:
        log.src(s)

    spot_results: dict = {}
    cache: dict = {}
    for sid, spot in kn.active_spots().items():
        try:
            data = collect_spot(http, spot, now, cache)
            res = features.build_spot(spot, data, now, kn.gates)
            for w in res["windows"]:
                w["gates"] = gates.spot_window_gates(spot, w, res["alerts"], res["alerts_checked"], kn.gates)
            spot_results[sid] = res
        except Exception as e:
            log.note(f"spot {sid} failed: {type(e).__name__}: {e} :: {traceback.format_exc(limit=3)[-400:]}")
    astro_src = log.src("astro")
    astro_src.update({"ok": bool(spot_results) or not kn.active_spots(), "n_calls": 0})

    dnr_res = dnr.fetch(http, kn.species)

    cands = cand_mod.build(kn, spot_results, dnr_res, now)
    cards = cards_mod.build_all(kn, cands, spot_results, now)

    sources_ok = {}
    for s in SOURCES:
        info = log.sources.get(s) or {}
        sources_ok[s] = bool(info.get("ok")) if info.get("n_calls") or s == "astro" else False
    latest = {
        "version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "run_time_et": now.isoformat(timespec="minutes"),
        "origin": {"name": (kn.profile.get("origin") or {}).get("name", "Frederick, MD"),
                   "lat": (kn.profile.get("origin") or {}).get("lat", 39.4143),
                   "lon": (kn.profile.get("origin") or {}).get("lon", -77.4105)},
        "sources_ok": sources_ok,
        "dnr": {k: dnr_res.get(k) for k in ("date", "link", "title", "by_species")},
        "spots": {sid: output.spot_out(kn, sid, res) for sid, res in spot_results.items()},
        "spots_listed": output.listed_only(kn, set(spot_results)),
        "candidates": [output.candidate_out(c) for c in cands],
        "cards": cards,
        "knowledge_version": kn.version(),
    }
    run_log = {"generated_at": latest["generated_at"], "run_time_et": latest["run_time_et"],
               "duration_s": None, "offline": bool(offline), **log.as_dict(),
               "counts": {"spots": len(spot_results), "candidates": len(cands), "cards": len(cards)}}
    run_log["duration_s"] = round(_time.time() - t0, 1)
    info = output.write(out_dir, latest, run_log, now)
    return {"latest": latest, "run_log": run_log, **info}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m engine.run")
    ap.add_argument("--offline", metavar="FIXTURE_DIR", help="replay recorded API responses from this directory")
    ap.add_argument("--record", metavar="DIR", help="save live API responses here (fixture layout)")
    ap.add_argument("--knowledge", metavar="DIR", help="knowledge directory (default: knowledge/)")
    ap.add_argument("--out", metavar="DIR", help="output directory (default: data/)")
    ap.add_argument("--now", metavar="ISO", help="pretend run time, e.g. 2026-10-14T05:00-04:00")
    a = ap.parse_args(argv)
    now = parse_time(a.now) if a.now else None
    try:
        res = run(a.knowledge, a.out, a.offline, a.record, now)
    except Exception as e:
        out = Path(a.out or ROOT / "data")
        out.mkdir(parents=True, exist_ok=True)
        import json
        (out / "run_log.json").write_text(json.dumps({
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "fatal": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-3000:]}, indent=1))
        print(traceback.format_exc(), file=sys.stderr)
        return 1
    rl = res["run_log"]
    print(f"7Fish run {rl['run_time_et']}: {rl['counts']['spots']} spots, {rl['counts']['candidates']} candidates, "
          f"{res['bytes'] / 1024:.0f} KB latest.json, {rl['duration_s']} s")
    for name, s in rl["sources"].items():
        print(f"  {name:10s} ok={s.get('ok')} calls={s.get('n_calls')} errors={len(s.get('errors') or [])}"
              + (f" skipped={s['skipped']}" if s.get("skipped") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
