/* ---------- Cast: the 7Fish forecaster ---------- */
I.cast = '<svg viewBox="0 0 28 26"><circle cx="14" cy="13" r="10.5" fill="none" stroke="currentColor" stroke-width="2.2"/><circle cx="14" cy="13" r="5.2" fill="none" stroke="currentColor" stroke-width="2.2"/><circle cx="14" cy="13" r="1.8" fill="currentColor"/></svg>';
const CAST_WHEN = [["Next 3 hrs", "next3h"], ["Tomorrow AM", "tomorrow_am"], ["Weekend", "weekend"]];
const CAST_TRIP = [["Quick", "quick"], ["Half day", "half"], ["Full day", "full"]];
const CAST_TIER = { Prime: 4, Good: 3, Fair: 2, Poor: 1 };
const CAST_CONF = { high: 3, medium: 2, low: 1 };
const CAST_INT = { high: 2, normal: 1, low: 0 };
const castOpt = (() => { let o = {}; try { o = JSON.parse(store.get("fod.cast") || "{}") || {}; } catch (e) { } return { when: o.when || "tomorrow_am", trip: o.trip || "half", luca: !!o.luca, target: o.target || "any" }; })();
const saveCastOpt = () => store.set("fod.cast", JSON.stringify(castOpt));
S.fcParts = {}; S.fc = null; S.ai = null; S.cast = { status: "idle" }; S.castCache = {};

function fcMerge() {
  const p = S.fcParts, m = p.meta;
  if (!m || !p.spots || !p.cands || !p.cards) return;
  if ([p.spots, p.cands, p.cards].some(x => x.generated_at !== m.generated_at)) return; // a sync is mid-write
  S.fc = { ...m, spots: p.spots.spots || {}, cands: p.cands.cands || [], cards: p.cards.cards || {} };
}
const etParts = d => Object.fromEntries(new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false, weekday: "short" }).formatToParts(d).map(x => [x.type, x.value]));
const etYMD = d => { const p = etParts(d); return `${p.year}-${p.month}-${p.day}`; };
const etTime = iso => iso ? new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: "America/New_York" }) : "—";
function winText(w) {
  if (!w) return "";
  const day = new Date(w.start).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric", timeZone: "America/New_York" });
  return `${day} · ${etTime(w.start)}–${etTime(w.end)} ET`;
}
const hasSpot = id => (S.spots || []).some(s => s.id === id);
const spotRow = (id, inner) => hasSpot(id) ? `<button class="row" data-go="spot:${esc(id)}">${inner}${I.chevR}</button>` : `<div class="row">${inner}</div>`;
function castWinMatch(when, w, now) {
  const s = new Date(w.start), e = new Date(w.end), date = w.id.split("|")[0];
  if (when === "next3h") return s < new Date(now.getTime() + 3 * 3600e3) && e > now;
  if (e <= now) return false;
  if (when === "tomorrow_am") { const t = new Date(now.getTime() + 864e5); return date === etYMD(t) && +etParts(s).hour < 12; }
  if (when === "weekend") { const wd = new Date(date + "T12:00:00").getDay(); const days = (new Date(date + "T12:00:00") - new Date(etYMD(now) + "T12:00:00")) / 864e5; return (wd === 0 || wd === 6) && days <= 6; }
  return false;
}
function castWindow(fc, spot, wid) { return ((fc.spots[spot] || {}).windows || []).find(w => w.id === wid); }
function castPool(fc, opt, now) {
  return fc.cands.filter(c => {
    const w = castWindow(fc, c.spot, c.window);
    if (!w || (w.fails || []).length) return false;
    if (!(c.trips || []).includes(opt.trip)) return false;
    if (opt.luca && !c.luca_ok) return false;
    return castWinMatch(opt.when, w, now);
  }).sort((a, b) => (CAST_TIER[b.tier] - CAST_TIER[a.tier]) || ((CAST_INT[b.interest] ?? 1) - (CAST_INT[a.interest] ?? 1)) || (CAST_CONF[b.confidence] - CAST_CONF[a.confidence]) || ((a.crowded ? 1 : 0) - (b.crowded ? 1 : 0)) || (a.drive_min - b.drive_min) || (new Date(castWindow(fc, a.spot, a.window).start) - new Date(castWindow(fc, b.spot, b.window).start)));
}
const c_spName = (fc, k) => ((fc.kn.species || {})[k] || {}).name || (SP[k] && SP[k].n) || k;
const spotName = (fc, id) => (fc.spots[id] || {}).name || id;

/* engine-style card, built on the phone: the fallback whenever Claude is unavailable or its card fails a check */
function castEngineCard(fc, opt, pool, now, note) {
  const top = opt.target !== "any" ? pool.find(c => c.species === opt.target) || null : pool[0] || null;
  if (!top) {
    const why = opt.target !== "any" ? `No legal, open, in-range window for ${c_spName(fc, opt.target)} in this slot.` : "Nothing clears the safety, rules and season checks in this slot.";
    return { verdict: "SKIP", headline: why, play: null, rig_line: null, source: "engine", note,
      details: { skip: { reason: why, closest_miss: pool[0] ? `${c_spName(fc, pool[0].species)} at ${spotName(fc, pool[0].spot)} (${pool[0].tier.toLowerCase()})` : "none" }, flips_it: "A different time slot or trip length.", confidence: "low", drivers: [] } };
  }
  const w = castWindow(fc, top.spot, top.window), sp = (fc.kn.species || {})[top.species] || {}, m = (sp.methods || [])[0] || {};
  const strong = top.tier === "Prime" || top.tier === "Good";
  const verdict = strong && top.confidence !== "low" ? "GO" : strong ? "GO IF" : "SKIP";
  const ks = (fc.kn.spots || {})[top.spot] || {}, pq = (ks.species || {})[top.species] || {};
  return {
    verdict, source: "engine", note,
    headline: `${verdict === "SKIP" ? "Best available: " : ""}${w.kind === "dawn" ? "Dawn" : w.kind === "dusk" ? "Dusk" : w.kind === "night" ? "Night" : "Daytime"} ${c_spName(fc, top.species).toLowerCase()} at ${spotName(fc, top.spot)}.`,
    condition: verdict === "GO IF" ? "Confidence is low: check the latest gauge or report before you drive." : null,
    play: { species_key: top.species, species: c_spName(fc, top.species), spot_id: top.spot, spot: spotName(fc, top.spot), window_id: top.window, window_text: winText(w), method: m.when || m.id || "" },
    rig_line: m.rig_line || null,
    details: {
      drivers: (top.reasons || []).slice(0, 3), confidence: top.confidence, confidence_note: top.confidence_note,
      pqa: { presence: { status: pq.presence === "verified" ? "verified" : "not verified" }, quality: { status: pq.quality === "verified" ? "verified" : "not verified" }, access: { status: ks.access_status === "verified" ? "verified" : "not verified", note: ks.parking || "" } },
      rig: { primary: m.rig_line, alternate: ((sp.methods || []).find(x => x.id === m.switch_to) || {}).rig_line, switch_trigger: m.switch_trigger, gear_note: m.gear_note },
      backup: pool[1] ? { text: `${c_spName(fc, pool[1].species)} at ${spotName(fc, pool[1].spot)}`, spot_id: pool[1].spot, species_key: pool[1].species, window_id: pool[1].window } : null,
      flips_it: "A fresh report or a gauge change; press Cast again after the next data update.",
      time: { drive_min: top.drive_min },
    },
  };
}

function castContext(fc, opt, pool, now) {
  const pick = [...pool.slice(0, 8)];
  if (opt.target !== "any") pool.filter(c => c.species === opt.target).slice(0, 4).forEach(c => { if (!pick.includes(c)) pick.push(c); });
  const spotIds = [...new Set(pick.map(c => c.spot))], spIds = [...new Set(pick.map(c => c.species).concat(opt.target !== "any" ? [opt.target] : []))];
  const regions = new Set(spotIds.map(s => (fc.spots[s] || {}).region));
  const spots = {};
  spotIds.forEach(id => {
    const s = fc.spots[id], wins = pick.filter(c => c.spot === id).map(c => c.window);
    spots[id] = { name: s.name, region: s.region, water_type: s.water_type, alerts: s.alerts, conditions: s.f,
      windows: s.windows.filter(w => wins.includes(w.id)).map(w => ({ id: w.id, text: winText(w), kind: w.kind, cond: w.cond })),
      knowledge: (fc.kn.spots || {})[id] };
  });
  const regs = {};
  spIds.forEach(k => { regs[k] = ((fc.kn.regs || {})[k] || []).filter(e => !e.regions || e.regions.some(r => regions.has(r))); });
  let targetNote = null;
  if (opt.target !== "any" && !pool.some(c => c.species === opt.target)) {
    const listed = Object.entries(fc.kn.spots || {}).filter(([, k]) => (k.species || {})[opt.target]).map(([id]) => id);
    targetNote = { target: opt.target, passing_rows_in_slot: 0, spots_listing_it: listed.map(id => ({ spot: id, name: spotName(fc, id),
      blocked_windows: ((fc.spots[id] || {}).windows || []).filter(w => castWinMatch(opt.when, w, now) && (w.fails || []).length).map(w => ({ id: w.id, fails: w.fails })) })),
      note: "No legal, open window passed the engine checks for this target in this slot (season, closures, safety, hours, drive limit, or no presence)." };
  }
  const trips = (S.trips || []).slice(-25).map(t => ({ date: t.date, spot: t.spot || t.spotName, catches: (t.catches || []).map(c => ({ sp: c.sp, n: c.n, len: c.len, on: c.on })), tactics: (t.tactics || []).map(x => ({ what: x.what, result: x.result, sp: x.sp })), notes: String(t.notes || "").slice(0, 160) }));
  return {
    request: { when: opt.when, trip: opt.trip, target: opt.target, luca: opt.luca, origin: "Frederick, MD" },
    run_time_et: now.toLocaleString("en-US", { timeZone: "America/New_York", dateStyle: "full", timeStyle: "short" }) + " ET",
    data_as_of: fc.run_time_et, sources_ok: fc.sources_ok,
    candidates: pick.map(c => ({ spot: c.spot, species: c.species, window: c.window, window_text: winText(castWindow(fc, c.spot, c.window)), tier: c.tier, confidence: c.confidence, confidence_note: c.confidence_note, drive_min: c.drive_min, trips: c.trips, luca_ok: c.luca_ok, interest: c.interest, crowded: c.crowded, reasons: c.reasons, methods: c.methods })),
    target_check: targetNote,
    spots, species: Object.fromEntries(spIds.map(k => [k, (fc.kn.species || {})[k]])), regs, regs_checked_on: fc.kn.regs_checked_on,
    dnr: fc.dnr ? { date: fc.dnr.date, title: fc.dnr.title, link: fc.dnr.link, by_species: Object.fromEntries(spIds.map(k => [k, ((fc.dnr.by_species || {})[k]) || []])) } : null,
    history: trips, profile: fc.kn.profile,
  };
}

const CAST_RULES = `You are the 7Fish Forecaster for Matt, a shore angler (no boat) based in Frederick, MD. Decide one thing: should Matt go fishing in the requested slot, and if so, exactly what fishing should he do. You are writing the card he reads before loading the truck.

You get JSON: REQUEST, RUN_TIME, CANDIDATES (spot × species × window rows that already passed every safety, legal, hours and season gate; tier words Prime/Good/Fair/Poor are the engine's condition fit), SPOTS (labeled conditions and knowledge), SPECIES (methods and rigs), REGS (with checked_on), DNR (latest Maryland report snippets), HISTORY (Matt's logged trips), PROFILE, and TARGET_CHECK when the named target had no passing rows.

Decision order, never reordered:
1. Safety and legality. Only recommend a row from CANDIDATES, using its exact spot, species and window ids. If none fits, the verdict is SKIP and you say why.
2. Named target. If REQUEST.target is not "any", judge it first and honestly. If it's poor or blocked, say so plainly in details.named_target, then give the best play for conditions. Never quietly substitute panfish or small bass.
3. Water and access. Flow, water temp, clarity, tide and Matt's firsthand notes outrank pressure and moon.
4. Fresh reports. Evidence within 30 days of RUN_TIME is current; a report with no catch date uses its report week. You may raise a row one tier at most, only by citing such a report. Lower freely, with a reason.
5. Pressure, moon and light are tie-breakers and timing, never the reason to go.
Profile: Matt's adult interests are catfish, snakehead, walleye, pike, musky, gar and striped bass. Bass is lower interest; recommend it only when the evidence is compelling and say why. He avoids crowds; crowded:true spots rank behind equal options.

Verdicts: GO = real evidence of quality, accessible water, conditions in or near the preferred band. GO IF = worth it under ONE condition Matt can check himself before or on the drive (a gauge reading, a time to be on the bank). SKIP = nothing clears the bar. A poor outlook is a valid answer.

Evidence rules (hard): keep Presence, Quality and Access separate and mark each verified / not verified. Never upgrade a label: forecast is not measured, air temp is not water temp. Never invent a reading, limit, depth or record; write "not found". Give catch dates separately from publish dates. Thin data lowers confidence, not fishing quality. No numeric scores, ratings or probabilities anywhere. Use actual dates with the year and ET clock times. Rules come only from REGS, quoted with checked_on; never from memory. If after-dark access is not verified, keep the plan in daylight.

If REQUEST.luca is true: simple bait fishing, an attainable target, clean bank, done by sunset. No adult predator priorities.

Card front stays short: verdict, one-sentence headline (max 140 chars), best play, one-line rig. Everything else goes in details. Voice: plain, specific, a little dry; at most one light line of humor. Commit to a call and name the main uncertainty once.

Reply with ONLY this JSON object (no prose):
{"verdict":"GO|GO IF|SKIP","headline":"...","condition":"GO IF only, else null","play":{"species_key":"","species":"","spot_id":"","spot":"","window_id":"","window_text":"","method":""} or null,"rig_line":"..." or null,"details":{"named_target":"... or null","drivers":[{"text":"","label":"measured|forecast|modeled|report|reasoning|not_found","src":""}],"confidence":"high|medium|low","confidence_note":"","pqa":{"presence":{"status":"verified|not verified","note":""},"quality":{"status":"","note":""},"access":{"status":"","note":""}},"rules":[{"text":"","checked_on":"","src":""}],"rig":{"primary":"","alternate":"","switch_trigger":"","gear_note":""},"backup":{"text":"","spot_id":"","species_key":"","window_id":""} or null,"flips_it":"","time":{"drive_min":0,"fishing_min":0,"away_min":0},"skip":{"reason":"","closest_miss":""} or null,"uncertainty":""}}
Up to 3 drivers. For SKIP, play and rig_line are null and details.skip is filled.`;

function castCheck(card, fc, pool) {
  if (!card || typeof card !== "object") return "no card";
  if (!["GO", "GO IF", "SKIP"].includes(card.verdict)) return "bad verdict";
  if (typeof card.headline !== "string" || !card.headline) return "no headline";
  const text = JSON.stringify(card);
  if (/\b\d{1,3}\s?%\s*(chance|probab|odds|likel)/i.test(text) || /\b(probability|score)\s*(of|:)\s*\d/i.test(text)) return "numeric probability";
  if (card.verdict === "SKIP") return null;
  const p = card.play;
  if (!p || !p.spot_id || !p.species_key || !p.window_id) return "GO card without a play";
  if (!pool.some(c => c.spot === p.spot_id && c.species === p.species_key && c.window === p.window_id)) return "play is not a passing candidate";
  if (castOpt.luca) { const c = pool.find(c => c.spot === p.spot_id && c.species === p.species_key && c.window === p.window_id); if (!c || !c.luca_ok) return "not a Luca-ok play"; }
  if (card.verdict === "GO IF" && !card.condition) return "GO IF without a condition";
  return null;
}

async function runCast(p, force) {
  const fc = S.fc; if (!fc || S.cast.status === "running") return;
  const now = new Date(), opt = { ...castOpt }, pool = castPool(fc, opt, now);
  const key = [opt.when, opt.trip, opt.luca, opt.target, fc.generated_at].join("|");
  if (!force && S.castCache[key]) { S.cast = { status: "done", ...S.castCache[key], cached: true }; p.render(); return; }
  if (!S.ai) {
    S.cast = { status: "done", key, card: castEngineCard(fc, opt, pool, now, "Claude isn't available in this view, so this is the engine's read.") }; p.render(); return;
  }
  const ctl = new AbortController();
  S.castAnim = CastScene.ok; S.cast = { status: "running", key, ctl, t0: Date.now() }; p.render();
  if (S.castAnim) { S.castAnim = CastScene.start(p.body.querySelector("#castSceneSlot"), () => ctl.abort()); if (!S.castAnim) p.render(); } // no WebGL: plain panel
  const prompt = CAST_RULES + "\n\nDATA:\n" + JSON.stringify(castContext(fc, opt, pool, now));
  let card, note = null;
  try {
    card = await S.ai.json(prompt, { signal: ctl.signal, modelTier: "default" });
    const bad = castCheck(card, fc, pool);
    if (bad) { note = `Claude's card failed a check (${bad}), so this is the engine's call.`; card = castEngineCard(fc, opt, pool, now, note); }
    else card.source = "claude";
  } catch (e) {
    if (e && e.code === "cancelled") { CastScene.stop(); S.castAnim = false; S.cast = { status: "idle" }; p.render(); return; }
    if (e && ["not_granted", "sampling_disabled", "not_declared", "capability_disabled", "capability_removed"].includes(e.code)) S.ai = null;
    const why = { rate_limited: "Claude is busy or your usage limit is reached; try again later.", not_granted: "Claude wasn't allowed for this page.", invalid_json: "Claude's answer came back garbled.", session_expired: "Sign in again to use Claude." }[e && e.code] || "Claude couldn't answer this time.";
    card = castEngineCard(fc, opt, pool, now, why + " This is the engine's read.");
  }
  const rec = { key, card, at: new Date().toISOString(), generated_at: fc.generated_at, request: opt };
  S.castCache[key] = rec;
  if (S.castAnim && CastScene.running) await new Promise(res => CastScene.finish(card, res));
  S.castAnim = false; S.cast = { status: "done", ...rec, fresh: true }; p.render();
  if (S.db && !S.sample) { try { await S.db.collection("casts").doc("c" + Date.now()).set({ ...rec, card: JSON.parse(JSON.stringify(card)) }); } catch (e) { } }
}

const lblTag = l => `<span class="lbltag ${esc(l || "")}">${esc(String(l || "").replace("_", " "))}</span>`;
function cardHTML(card, fc) {
  const cls = card.verdict === "GO" ? "go" : card.verdict === "GO IF" ? "goif" : "skip", d = card.details || {}, p = card.play;
  let h = `<article class="vcard ${cls}"><div class="vtop"><div class="vk">${card.source === "claude" ? "Claude's call" : "Engine read"}</div><div class="vword">${esc(card.verdict)}</div><div class="vhead">${esc(card.headline)}</div>${card.condition ? `<div class="vcond"><b>Only if:</b> ${esc(card.condition)}</div>` : ""}</div><div class="vbody">`;
  if (p) {
    h += `<div class="group" style="background:transparent">` +
      `<div class="row"><span class="k">Target</span><div class="main"><div class="ti">${esc(p.species)}</div></div></div>` +
      spotRow(p.spot_id, `<span class="k">Where</span><div class="main"><div class="ti">${esc(p.spot)}</div></div>`) +
      `<div class="row"><span class="k">When</span><div class="main"><div class="ti">${esc(p.window_text || winText(castWindow(fc, p.spot_id, p.window_id)))}</div></div></div>` +
      (p.method ? `<div class="row"><span class="k">How</span><div class="main"><div class="ti">${esc(p.method)}</div></div></div>` : "") +
      (card.rig_line ? `<div class="row"><span class="k">Rig</span><div class="main"><div class="rigline">${esc(card.rig_line)}</div></div></div>` : "") + `</div>`;
  } else if (d.skip) {
    h += `<div class="group" style="background:transparent"><div class="row"><span class="k">Why</span><div class="main"><div class="ti">${esc(d.skip.reason)}</div></div></div>${d.skip.closest_miss ? `<div class="row"><span class="k">Closest</span><div class="main"><div class="ti">${esc(d.skip.closest_miss)}</div></div></div>` : ""}</div>`;
  }
  const s = p ? fc.spots[p.spot_id] : null;
  h += `<div class="vacts"><button id="castMore" aria-expanded="${!!S.castOpen}">${S.castOpen ? "Hide details" : "Details"}</button>${s ? `<a class="pri" href="https://maps.apple.com/?daddr=${s.lat},${s.lon}&dirflg=d" target="_blank" rel="noopener">${I.pin}Directions</a>` : ""}</div>`;
  if (card.note) h += `<div class="src">${esc(card.note)}</div>`;
  h += `</div></article>`;
  if (S.castOpen) h += detailsHTML(card, fc);
  return h;
}
function detailsHTML(card, fc) {
  const d = card.details || {}, rows = [];
  let h = "";
  if (d.named_target) h += `<div class="gh">Your target</div><div class="group"><div class="row"><div class="main"><div class="ti wrap2">${esc(d.named_target)}</div></div></div></div>`;
  if ((d.drivers || []).length) h += `<div class="gh">Why</div><div class="group">${d.drivers.map(x => `<div class="row"><div class="main"><div class="ti wrap2">${lblTag(x.label)}${esc(x.text)}</div>${x.src ? `<div class="su">${esc(x.src)}</div>` : ""}</div></div>`).join("")}</div>`;
  if (d.confidence) h += `<div class="gh">Confidence</div><div class="group"><div class="row"><div class="main"><div class="ti wrap2"><b>${esc(d.confidence[0].toUpperCase() + d.confidence.slice(1))}</b>${d.confidence_note ? ` · ${esc(d.confidence_note)}` : ""}</div><div class="su wrap2">Confidence is about the data, not the bite.</div></div></div></div>`;
  if (d.pqa) {
    const c = k => { const x = d.pqa[k] || {}, ok = x.status === "verified"; return `<div><b>${k}</b><span class="${ok ? "ok" : "no"}">${esc(x.status || "not verified")}</span>${x.note ? `<p>${esc(x.note)}</p>` : ""}</div>`; };
    h += `<div class="gh">The three questions</div><div class="pqa">${c("presence")}${c("quality")}${c("access")}</div>`;
  }
  const r = d.rig || {};
  if (r.primary || r.alternate) h += `<div class="gh">Rig</div><div class="group">${r.primary ? `<div class="row"><div class="main"><div class="su">Primary</div><div class="rigline">${esc(r.primary)}</div></div></div>` : ""}${r.alternate ? `<div class="row"><div class="main"><div class="su">Switch to</div><div class="rigline">${esc(r.alternate)}</div>${r.switch_trigger ? `<div class="su wrap2">When: ${esc(r.switch_trigger)}</div>` : ""}</div></div>` : ""}${r.gear_note ? `<div class="row"><div class="main"><div class="su wrap2">${esc(r.gear_note)}</div></div></div>` : ""}</div>`;
  if ((d.rules || []).length) h += `<div class="gh">Rules</div><div class="group">${d.rules.map(x => `<div class="row"><div class="main"><div class="ti wrap2">${esc(x.text)}</div><div class="su">${x.checked_on ? "Checked " + esc(x.checked_on) : ""}${x.src ? ` · <a href="${esc(x.src)}" target="_blank" rel="noopener">source</a>` : ""}</div></div></div>`).join("")}</div>`;
  const t = d.time || {};
  if (t.drive_min || t.away_min) h += `<div class="gh">Time</div><div class="group">${t.drive_min ? `<div class="row"><div class="main"><div class="ti">Drive each way</div></div><span class="val">~${Math.round(t.drive_min)} min</span></div>` : ""}${t.fishing_min ? `<div class="row"><div class="main"><div class="ti">Fishing</div></div><span class="val">~${Math.round(t.fishing_min / 60 * 10) / 10} h</span></div>` : ""}${t.away_min ? `<div class="row"><div class="main"><div class="ti">Time away</div></div><span class="val">~${Math.round(t.away_min / 60 * 10) / 10} h</span></div>` : ""}</div>`;
  if (d.backup && d.backup.text) rows.push(["Backup", d.backup.text]);
  if (d.flips_it) rows.push(["What flips it", d.flips_it]);
  if (d.uncertainty) rows.push(["Main uncertainty", d.uncertainty]);
  if (rows.length) h += `<div class="gh">Also</div><div class="group">${rows.map(([k, v]) => `<div class="row"><div class="main"><div class="su">${esc(k)}</div><div class="ti wrap2">${esc(v)}</div></div></div>`).join("")}</div>`;
  return h;
}
function waterNowHTML(fc) {
  const ids = Object.keys(fc.spots);
  const fmt = (x, u) => x && x.v != null ? `${Math.round(x.v * (u === "cfs" ? 1 : 10)) / (u === "cfs" ? 1 : 10)}${u === "degF" ? "°F" : " " + u}` : "—";
  return `<div class="gh">Water now</div><div class="group wnow">${ids.map(id => {
    const s = fc.spots[id], f = s.f || {}, wt = f.water_temp || {}, fl = (f.flow || {}).now, cl = f.clarity || {};
    const sub = [wt.v != null ? `${fmt(wt, "degF")} ${wt.label} · ${wt.src}${wt.dist_mi ? ` (${Math.round(wt.dist_mi)} mi)` : ""}` : "water temp not found",
      fl && fl.v != null ? `${Math.round(fl.v).toLocaleString()} cfs ${(f.flow || {}).trend || ""}` : null,
      f.pressure && f.pressure.class ? `pressure ${f.pressure.class}` : null].filter(Boolean).join(" · ");
    return spotRow(id, `<div class="main"><div class="ti">${esc(s.name)}</div><div class="su wrap2">${esc(sub)}</div></div><span class="val">${esc(String(cl.v || "").replace("likely_", "").replace("_", " "))}</span>`);
  }).join("")}</div><div class="gf">Clarity is a guess from rain and flow. Every reading carries its source and distance in the details.</div>`;
}

function castPage() {
  return {
    title: "Cast", cls: "hx", build(p) {
      const fc = S.fc, now = new Date();
      const age = fc ? (now - new Date(fc.generated_at)) / 36e5 : null;
      const fresh = fc ? `<div class="freshness ${age > 12 ? "old" : age > 3 ? "stale" : ""}"><span class="dot"></span><span>${age > 12 ? "Stale data · " : ""}Conditions as of ${esc(etTime(fc.generated_at))}${age > 20 ? ` (${Math.round(age / 24)} d ago)` : ""} · ${Object.keys(fc.spots).length} spots</span></div>` : `<div class="freshness old"><span class="dot"></span><span>${S.live === false ? "Open this in Claude to load the forecast." : "Loading the forecast…"}</span></div>`;
      const running = S.cast.status === "running";
      const tgtLbl = castOpt.target === "any" ? "Any target" : (fc ? c_spName(fc, castOpt.target) : castOpt.target);
      const extra = `<div class="castwrap"><button class="castbtn ${running ? "busy" : ""}" id="castGo" ${!fc || running ? "disabled" : ""} aria-label="Cast: should I go fishing?">Cast<small>${running ? "reading…" : "go or no"}</small></button>
        <div class="ctl"><div class="lbl">When</div><div class="seg" id="cWhen"></div><div class="lbl">Trip</div><div class="seg" id="cTrip"></div>
        <div class="chips"><button class="chip" id="cTgt" aria-haspopup="menu">${esc(tgtLbl)}${I.caret}</button><button class="chip" id="cLuca" aria-pressed="${castOpt.luca}">With Luca</button></div></div>${fresh}</div>`;
      let h = hero("Cast", "Press it. Get a go, a go-if, or a skip.", extra, "7FISH FORECAST") + `<div class="wrap">`;
      if (running && S.castAnim) h += `<div class="castscene-slot" id="castSceneSlot"></div>`;
      else if (running) h += `<div class="thinking"><h3>Reading the water</h3><p>Claude is weighing ${fc ? castPool(fc, castOpt, now).length : 0} open windows against flow, temp, tides, reports and your log.</p><div class="bar"><i></i></div><button class="cap" id="castStop">Stop</button></div>`;
      else if (S.cast.status === "done" && S.cast.card) h += cardHTML(S.cast.card, fc) + (S.cast.cached ? `<div class="gf" style="text-align:center">Same data and settings as your last cast. <button class="sortb" id="castAgain" style="height:28px">Cast again</button></div>` : "");
      else if (fc) h += `<p class="emptycast">Set the slot, then press <b>Cast</b>. Claude reads ${Object.keys(fc.spots).length} spots, ${fc.cands.length} open windows and your trip log, then makes one call.</p>`;
      if (fc) h += waterNowHTML(fc);
      p.body.innerHTML = h + `</div>`;
      const q = s => p.body.querySelector(s);
      segment(q("#cWhen"), CAST_WHEN.map(x => x[0]), CAST_WHEN.findIndex(x => x[1] === castOpt.when), i => { castOpt.when = CAST_WHEN[i][1]; saveCastOpt(); S.cast = { status: "idle" }; p.render(); });
      segment(q("#cTrip"), CAST_TRIP.map(x => x[0]), CAST_TRIP.findIndex(x => x[1] === castOpt.trip), i => { castOpt.trip = CAST_TRIP[i][1]; saveCastOpt(); S.cast = { status: "idle" }; p.render(); });
      q("#cLuca").onclick = () => { castOpt.luca = !castOpt.luca; saveCastOpt(); S.cast = { status: "idle" }; p.render(); };
      q("#cTgt").onclick = e => {
        const sp = fc ? Object.entries(fc.kn.species || {}).map(([k, v]) => [v.name || k, k]).sort((a, b) => a[0].localeCompare(b[0])) : [];
        menu(e.currentTarget, "Target", [["Any target", "any"], ...sp], castOpt.target, v => { castOpt.target = v; saveCastOpt(); S.cast = { status: "idle" }; p.render(); });
      };
      const go = q("#castGo"); if (go) go.onclick = () => { S.castOpen = false; runCast(p, false); };
      const slot = q("#castSceneSlot"); if (slot) CastScene.mount(slot);
      if (S.cast.fresh) { const vc = q(".vcard"); if (vc) vc.classList.add("pop"); S.cast.fresh = false; }
      const st = q("#castStop"); if (st) st.onclick = () => S.cast.ctl && S.cast.ctl.abort();
      const ag = q("#castAgain"); if (ag) ag.onclick = () => runCast(p, true);
      const mo = q("#castMore"); if (mo) mo.onclick = () => { S.castOpen = !S.castOpen; p.render(); };
    },
  };
}
