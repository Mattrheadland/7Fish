"""Maryland DNR weekly fishing report via the WordPress JSON API.

GET https://news.maryland.gov/dnr/wp-json/wp/v2/posts?search=fishing%20report&per_page=3&_fields=date,link,title,content
  -> [{"date": "2026-10-08T12:00:00", "link": "...", "title": {"rendered": "..."}, "content": {"rendered": "<p>...</p>"}}]

Stores only: date, link, title and at most 3 short sentences (<= 240 chars) per species.
The full article text is never stored or returned.
"""
from __future__ import annotations

import html
import re

from ..util import ET, parse_time

URL = "https://news.maryland.gov/dnr/wp-json/wp/v2/posts"
SRC = "dnr"
MAX_SENT = 3
MAX_CHARS = 240

DEFAULT_ALIASES = {
    "striped-bass": ["striped bass", "striper", "rockfish"],
    "white-perch": ["white perch"],
    "channel-catfish": ["channel catfish", "channel cat"],
    "blue-catfish": ["blue catfish", "blue cat"],
    "flathead-catfish": ["flathead catfish", "flathead"],
    "northern-snakehead": ["snakehead"],
    "walleye": ["walleye"],
    "smallmouth-bass": ["smallmouth bass", "smallmouth"],
    "largemouth-bass": ["largemouth bass", "largemouth"],
    "red-drum": ["red drum", "redfish", "puppy drum"],
    "bluefish": ["bluefish"],
    "spotted-seatrout": ["speckled trout", "spotted seatrout", "specks"],
    "muskellunge": ["muskellunge", "musky", "muskie"],
    "northern-pike": ["northern pike"],
    "longnose-gar": ["longnose gar"],
}


def _strip_html(s: str) -> str:
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s or "", flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"“])")


def _shorten(s: str) -> str:
    s = s.strip()
    if len(s) <= MAX_CHARS:
        return s
    cut = s[:MAX_CHARS - 1]
    cut = cut[:cut.rfind(" ")] if " " in cut else cut
    return cut.rstrip(",;:") + "…"


def extract(text: str, aliases: dict[str, list[str]]) -> dict[str, list[str]]:
    sents = _SENT.split(text)
    out: dict[str, list[str]] = {}
    for key, names in aliases.items():
        pats = [re.compile(r"\b" + re.escape(n.lower()) + r"s?\b") for n in names if n]
        hits = []
        for s in sents:
            low = s.lower()
            if any(p.search(low) for p in pats):
                hits.append(_shorten(s))
                if len(hits) >= MAX_SENT:
                    break
        if hits:
            out[key] = hits
    return out


def build_aliases(species: dict) -> dict[str, list[str]]:
    al = {}
    for key, sp in species.items():
        names = list(DEFAULT_ALIASES.get(key, []))
        nm = sp.get("name")
        if nm and nm.lower() not in names:
            names.append(nm.lower())
        for a in sp.get("aliases") or []:
            if isinstance(a, str) and a.lower() not in names:
                names.append(a.lower())
        al[key] = names
    return al


def fetch(http, species: dict) -> dict:
    out = {"date": None, "link": None, "title": None, "by_species": {}, "ok": False}
    try:
        params = {"search": "fishing report", "per_page": 3, "_fields": "date,link,title,content"}
        data = http.get_json(SRC, URL, params=params, key="posts")
        posts = [p for p in (data or []) if isinstance(p, dict)] if isinstance(data, list) else []
        posts = [p for p in posts if "fishing report" in _strip_html(_title(p)).lower()] or posts
        posts.sort(key=lambda p: str(p.get("date") or ""), reverse=True)
        if not posts:
            return out
        p = posts[0]
        t = parse_time(p.get("date"), assume_tz=ET)
        out["date"] = t.date().isoformat() if t else None
        out["link"] = p.get("link")
        out["title"] = _strip_html(_title(p))[:160]
        text = _strip_html(((p.get("content") or {}).get("rendered")) if isinstance(p.get("content"), dict) else str(p.get("content") or ""))
        out["by_species"] = extract(text, build_aliases(species))
        out["ok"] = True
        del text
    except Exception as e:
        http.log.error(SRC, f"{type(e).__name__}: {e}")
    return out


def _title(p):
    t = p.get("title")
    if isinstance(t, dict):
        return t.get("rendered") or ""
    return str(t or "")
