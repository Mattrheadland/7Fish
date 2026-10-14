"""HTTP access for every collector.

One session, one User-Agent, 20 s timeout, one retry. Every call is logged into the
run log under sources.<name>. The first successful response's shape (top-level keys and,
for GeoJSON, the first feature's property keys) is stored under sources.<name>.shape so a
parse mismatch can be diagnosed from the committed run_log.json.

Offline mode replays recorded JSON from a fixture directory instead of the network:
    <dir>/<source>/<key>.json      exact match for this call
    <dir>/<source>/<kind>.json     fallback, kind = key before the first "__"
Record mode (--record DIR) writes live responses in the same layout.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests

USER_AGENT = "7Fish (github.com/Mattrheadland/7Fish)"
TIMEOUT_S = 20
MAX_CALL_LOG = 40          # per source, keeps run_log.json small
MAX_ERRORS = 20


def _safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.,-]+", "_", s)[:150]


def describe_shape(data: Any) -> dict:
    """Small structural summary of a JSON response for diagnosis."""
    shape: dict = {"type": type(data).__name__}
    if isinstance(data, dict):
        shape["keys"] = sorted(list(data.keys()))[:40]
        feats = data.get("features")
        if isinstance(feats, list):
            shape["n_features"] = len(feats)
            if feats and isinstance(feats[0], dict):
                props = feats[0].get("properties")
                if isinstance(props, dict):
                    shape["feature_property_keys"] = sorted(props.keys())[:40]
        props = data.get("properties")
        if isinstance(props, dict):
            shape["property_keys"] = sorted(props.keys())[:40]
    elif isinstance(data, list):
        shape["len"] = len(data)
        if data and isinstance(data[0], dict):
            shape["item_keys"] = sorted(data[0].keys())[:40]
    return shape


class RunLog:
    def __init__(self) -> None:
        self.sources: dict[str, dict] = {}
        self.notes: list[str] = []
        self.knowledge: dict = {}

    def src(self, name: str) -> dict:
        return self.sources.setdefault(
            name, {"ok": None, "n_calls": 0, "n_ok": 0, "errors": [], "shape": None, "calls": []}
        )

    def call(self, name: str, url: str, status: Any, ms: int, ok: bool, err: str | None = None) -> None:
        s = self.src(name)
        s["n_calls"] += 1
        if ok:
            s["n_ok"] += 1
        if len(s["calls"]) < MAX_CALL_LOG:
            s["calls"].append({"url": url[:300], "status": status, "ms": ms})
        if err and len(s["errors"]) < MAX_ERRORS:
            s["errors"].append(err[:300])
        s["ok"] = s["n_ok"] > 0

    def error(self, name: str, msg: str) -> None:
        s = self.src(name)
        if len(s["errors"]) < MAX_ERRORS:
            s["errors"].append(msg[:300])

    def skipped(self, name: str, why: str) -> None:
        s = self.src(name)
        s["skipped"] = why

    def shape(self, name: str, data: Any, label: str | None = None) -> None:
        s = self.src(name)
        key = "shape" if label is None else f"shape_{label}"
        if s.get(key) is None:
            s[key] = describe_shape(data)

    def note(self, msg: str) -> None:
        self.notes.append(msg[:300])

    def as_dict(self) -> dict:
        return {"sources": self.sources, "notes": self.notes, "knowledge": self.knowledge}


class Http:
    def __init__(self, log: RunLog, offline_dir: str | None = None, record_dir: str | None = None,
                 sleep_between_retries: float = 2.0) -> None:
        self.log = log
        self.offline_dir = Path(offline_dir) if offline_dir else None
        self.record_dir = Path(record_dir) if record_dir else None
        self.sleep = sleep_between_retries
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/geo+json, application/json"})

    # ------------------------------------------------------------------
    def get_json(self, source: str, url: str, params: dict | None = None, key: str = "default",
                 headers: dict | None = None, shape_label: str | None = None) -> Any:
        """Return parsed JSON or None. Never raises."""
        if self.offline_dir is not None:
            return self._offline(source, url, key, shape_label)
        full = url
        last_err = None
        for attempt in range(2):
            t0 = time.time()
            try:
                r = self.session.get(url, params=params, timeout=TIMEOUT_S, headers=headers)
                full = r.url
                ms = int((time.time() - t0) * 1000)
                if r.status_code >= 400:
                    last_err = f"HTTP {r.status_code} {full[:200]} :: {r.text[:150]}"
                    self.log.call(source, _redact(full), r.status_code, ms, False, last_err)
                    if r.status_code in (400, 401, 403, 404):
                        break  # retry won't help
                else:
                    data = r.json()
                    self.log.call(source, _redact(full), r.status_code, ms, True)
                    self.log.shape(source, data, shape_label)
                    if self.record_dir is not None:
                        p = self.record_dir / source / f"{_safe_name(key)}.json"
                        p.parent.mkdir(parents=True, exist_ok=True)
                        p.write_text(json.dumps(data))
                    return data
            except Exception as e:  # network, JSON, anything
                ms = int((time.time() - t0) * 1000)
                last_err = f"{type(e).__name__}: {str(e)[:200]}"
                self.log.call(source, _redact(full), None, ms, False, last_err)
            if attempt == 0 and self.sleep:
                time.sleep(self.sleep)
        return None

    def _offline(self, source: str, url: str, key: str, shape_label: str | None) -> Any:
        base = self.offline_dir / source
        cands = [base / f"{_safe_name(key)}.json"]
        kind = key.split("__", 1)[0]
        cands.append(base / f"{_safe_name(kind)}.json")
        for p in cands:
            if p.exists():
                try:
                    data = json.loads(p.read_text())
                except Exception as e:
                    self.log.call(source, f"offline:{p.name}", None, 0, False, f"bad fixture {p}: {e}")
                    return None
                self.log.call(source, f"offline:{p.name}", 200, 0, True)
                self.log.shape(source, data, shape_label)
                return data
        self.log.call(source, f"offline:{key}", 404, 0, False, f"no fixture for {source}/{key}")
        return None


def _redact(url: str) -> str:
    return re.sub(r"(key=)[^&]+", r"\1***", url)


def env_key(name: str) -> str | None:
    v = os.environ.get(name, "").strip()
    return v or None
