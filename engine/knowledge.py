"""Load the knowledge YAML. Tolerant of missing files, partial files and unknown keys.

Nothing here raises on bad content: a broken file is logged and skipped.
"""
from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

import yaml

TIER_WORDS = ["closed", "absent", "poor", "fair", "good", "prime"]

DEFAULT_PROFILE = {
    "origin": {"name": "Frederick, MD", "lat": 39.4143, "lon": -77.4105},
    "trip_types": {
        "quick": {"max_drive_min": 35, "fishing_min": 120},
        "half": {"max_drive_min": 95, "fishing_min": 240},
        "full": {"max_drive_min": 190, "fishing_min": 420},
    },
    "setup_overhead_min": 20,
}

DEFAULT_GATES = {
    "alerts": {
        "all_spots": [
            "Severe Thunderstorm Warning", "Severe Thunderstorm Watch", "Tornado Warning", "Tornado Watch",
            "Flood Warning", "Flash Flood Warning", "High Wind Warning", "Gale Warning",
        ],
        "water_types": {"pier": ["Small Craft Advisory"], "inlet": ["Small Craft Advisory"]},
        "not_gates": ["Heat Advisory"],
    },
    "thunder_keywords": ["thunder", "t-storm", "tstorm"],
    "wind": {"default_gust_limit_mph": 30, "near_limit_mph": 5},
    "flow": {"ceiling_fallback": "nwps_action_stage", "near_fraction": 0.85, "block_categories": ["action", "minor", "moderate", "major"]},
    "hours": {"min_window_min": 60},
    "water_temp": {"max_station_dist_mi": 25, "max_age_h": 36},
    "clarity": {"muddy_rain_48h_in": 0.75, "clear_rain_48h_in": 0.1, "muddy_flow_rise_48h": 0.30,
                "turbidity_muddy_ntu": 25, "turbidity_clear_ntu": 10},
    "pressure": {"class_inhg_24h": 0.06, "front_inhg_24h": 0.10},
    "tide": {"slack_min": 45},
    "dnr": {"fresh_days": 30},
}


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _load_yaml(path: Path, log=None):
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        if log is not None:
            log.note(f"knowledge: cannot parse {path.name}: {type(e).__name__}: {str(e)[:150]}")
        return None


def norm_status(s) -> str:
    """'not_verified' / 'not verified' / 'ruled-out' -> schema words."""
    if s is None:
        return "not verified"
    s = str(s).strip().lower().replace("_", " ").replace("-", " ")
    if s in ("verified", "documented"):
        return "verified"
    if s in ("ruled out", "rejected"):
        return "ruled out"
    return "not verified"


def is_ruled_out(s) -> bool:
    return norm_status(s) == "ruled out"


class Knowledge:
    def __init__(self, root: str | Path, log=None):
        self.root = Path(root)
        self.log = log
        self.species: dict[str, dict] = {}
        self.spots: dict[str, dict] = {}
        self.regs: dict = {}
        self.gates: dict = DEFAULT_GATES
        self.profile: dict = DEFAULT_PROFILE
        self.problems: list[str] = []
        self._load()

    def _p(self, msg):
        self.problems.append(msg)
        if self.log is not None:
            self.log.note(msg)

    def _load(self):
        for p in sorted((self.root / "species").glob("*.yaml")):
            d = _load_yaml(p, self.log)
            if not isinstance(d, dict):
                self._p(f"knowledge: species/{p.name} empty or unreadable, skipped")
                continue
            key = d.get("key") or p.stem
            d["key"] = key
            d.setdefault("name", key.replace("-", " ").capitalize())
            self.species[key] = d
        for p in sorted((self.root / "spots").glob("*.yaml")):
            d = _load_yaml(p, self.log)
            if not isinstance(d, dict):
                self._p(f"knowledge: spots/{p.name} empty or unreadable, skipped")
                continue
            sid = d.get("id") or p.stem
            d["id"] = sid
            lat, lon = d.get("lat"), d.get("lon")
            if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
                self._p(f"knowledge: spot {sid} has no numeric lat/lon; listed but not forecast")
                d["_no_coords"] = True
            d.setdefault("name", sid)
            d.setdefault("status", "active")
            self.spots[sid] = d
        regs = _load_yaml(self.root / "rules" / "regs.yaml", self.log)
        self.regs = regs if isinstance(regs, dict) else {}
        if not self.regs:
            self._p("knowledge: rules/regs.yaml missing or empty; no closure gates applied, rules show 'not found'")
        gates = _load_yaml(self.root / "rules" / "gates.yaml", self.log)
        self.gates = _deep_merge(DEFAULT_GATES, gates if isinstance(gates, dict) else {})
        prof = _load_yaml(self.root / "profile.yaml", self.log)
        self.profile = _deep_merge(DEFAULT_PROFILE, prof if isinstance(prof, dict) else {})

    # ------------------------------------------------------------------
    def active_spots(self) -> dict[str, dict]:
        return {k: v for k, v in self.spots.items()
                if not is_ruled_out(v.get("status")) and not v.get("_no_coords")}

    def season_word(self, species_key: str, region: str, month: int) -> str | None:
        sp = self.species.get(species_key) or {}
        season = sp.get("season") or {}
        row = season.get(region)
        if not isinstance(row, dict):
            return None
        w = row.get(month, row.get(str(month)))
        if w is None:
            return None
        w = str(w).strip().lower()
        return w if w in TIER_WORDS else None

    def regs_for(self, species_key: str, region: str) -> list[dict]:
        out = []
        for entry in (self.regs.get("species") or {}).get(species_key) or []:
            if not isinstance(entry, dict):
                continue
            regions = entry.get("regions") or []
            if not regions or region in regions:
                out.append(entry)
        return out

    def targeting_closed(self, species_key: str, region: str, d: date):
        """Return (closed: bool, note) using MM-DD inclusive ranges (wraps year end)."""
        for entry in self.regs_for(species_key, region):
            for rng in entry.get("targeting_closed") or []:
                if isinstance(rng, dict) and _in_mmdd(d, rng.get("start"), rng.get("end")):
                    return True, (rng.get("note") or entry.get("area") or "targeting closed"), entry.get("src")
        return False, None, None

    def version(self) -> str:
        try:
            sha = subprocess.run(["git", "-C", str(self.root), "rev-parse", "--short", "HEAD"],
                                 capture_output=True, text=True, timeout=5).stdout.strip()
            if sha:
                return sha
        except Exception:
            pass
        return date.today().isoformat()


def _in_mmdd(d: date, start, end) -> bool:
    try:
        sm, sd = (int(x) for x in str(start).split("-"))
        em, ed = (int(x) for x in str(end).split("-"))
    except Exception:
        return False
    cur = (d.month, d.day)
    s, e = (sm, sd), (em, ed)
    if s <= e:
        return s <= cur <= e
    return cur >= s or cur <= e
