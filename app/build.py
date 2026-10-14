"""Splice the Cast screen into the 7 Fish page.

base-7fish.html is the page as it was before Cast (version from 2026-10-14). The build inserts
cast.css before the main style block closes, the Cast layer and tab, and cast-scene.js + cast.js
before boot(). Output: 7fish-app.html (publish that file to the artifact).
"""
import re
from pathlib import Path

D = Path(__file__).parent
s = (D / "base-7fish.html").read_text()
css = (D / "cast.css").read_text()
js = (D / "cast-scene.js").read_text() + "\n" + (D / "cast.js").read_text()


def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:80])
    s = s.replace(old, new)


i = s.index('<div class="layer" id="L-log">'); j = s.rfind("</style>", 0, i); s = s[:j] + css + "\n" + s[j:]
rep('<div class="layer" id="L-log"></div>', '<div class="layer" id="L-cast" hidden></div><div class="layer" id="L-log" hidden></div>')
rep('const NAV = { log: [], plan: [], map: [], vault: [], ins: [] };', 'const NAV = { cast: [], log: [], plan: [], map: [], vault: [], ins: [] };')
rep('const ROOT = { log: journalPage, plan: planPage, map: chartPage, vault: vaultPage, ins: insightsPage };', 'const ROOT = { cast: castPage, log: journalPage, plan: planPage, map: chartPage, vault: vaultPage, ins: insightsPage };')
rep('const TABNAME = { log: "Logbook", plan: "Planner", map: "Chart", vault: "Findex", ins: "Intel" };', 'const TABNAME = { cast: "Cast", log: "Logbook", plan: "Planner", map: "Chart", vault: "Findex", ins: "Intel" };')
rep('tab: ["log", "plan", "map", "vault", "ins"].includes(store.get("fod.tab")) ? store.get("fod.tab") : "log",', 'tab: ["cast", "log", "plan", "map", "vault", "ins"].includes(store.get("fod.tab7")) ? store.get("fod.tab7") : "cast",')
rep('S.tab = t; store.set("fod.tab", t);', 'S.tab = t; store.set("fod.tab7", t);')
rep('$("#tabbar").innerHTML = ["log", "plan", "map", "vault", "ins"].map(', '$("#tabbar").innerHTML = ["cast", "log", "plan", "map", "vault", "ins"].map(')
rep('["log", "plan", "map", "vault", "ins"].forEach(t => $("#L-" + t).hidden = t !== S.tab);', '["cast", "log", "plan", "map", "vault", "ins"].forEach(t => $("#L-" + t).hidden = t !== S.tab);')
rep("\nfunction boot() {", "\n" + js + "\nfunction boot() {")
rep('  cl.use("assets").then(a => {', '''  sub("forecast", rows => { rows.forEach(r => { S.fcParts[r.id] = r; }); fcMerge(); });
  sub("casts", rows => { rows.sort((a, b) => String(a.at).localeCompare(String(b.at))).forEach(r => { if (r.key && r.card) S.castCache[r.key] = r; }); });
  cl.use("sample").then(fn => { S.ai = fn || null; refreshAll(); }).catch(() => { S.ai = null; });
  cl.use("assets").then(a => {''')
(D / "7fish-app.html").write_text(s)
(D / "_main.js").write_text(re.findall(r"<script>(.*?)</script>", s, re.S)[-1])
print("built", len(s), "bytes")
