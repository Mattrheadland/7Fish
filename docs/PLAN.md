# 7Fish Forecast — Build Plan v1.1

Prepared October 14, 2026. Status: planned, not built. v1.1 folds in the independent peer review (see REVIEW.md).

## 1. What it is

One button. Press **Cast** and 7Fish tells you whether to go fishing, and if so, what kind: target, water, window, method, rig. Everything heavy (weather history, pressure trends, river forecasts, water temp, tides, moon, reports, species biology, access rules, your own trip log) happens out of sight.

It lives inside the existing 7 Fish app as the home screen, so forecasts and trip logs share one database and every trip you log grades the forecast that sent you there.

## 2. What the button returns

**The card (what you see):**
- **Verdict**: GO · GO IF… · SKIP. Words only, never a score or percentage.
- **Headline**: "Dawn blue cats on the tidal Potomac. Worth the drive."
- **Best play**: species, spot, window (date, year, clock times ET).
- **Rig**: one line ("8/0 circle, 3 oz no-roll on a fish-finder slide, 50 lb mono leader 24 in, cut menhaden").
- For GO IF…, the condition is something you can check from the truck ("only if the Point of Rocks gauge reads under X ft at 5 AM").

**Details (one tap, a sheet):** up to three labeled drivers (measured / forecast / modeled / report / reasoning), confidence (separate from quality), Presence-Quality-Access status, rules with checked-on dates, alternate rig and switch trigger, backup play, what flips the call, time away, and data freshness.

**Chips (optional):** When (Next 3 hrs / Tomorrow AM / Weekend), Trip (Quick / Half / Full), Target (Any or a species), Luca (off/on). Defaults: Any, Half day, Tomorrow AM, Frederick origin. Untouched chips mean you just press Cast.

SKIP is a real answer. If your named target is having a bad day, the card says so and puts the best play for conditions underneath.

## 3. Architecture

Code measures, Claude judges, the app just displays. The whole pipeline runs in GitHub Actions, which has open internet and a free scheduler.

```
GitHub Actions  (03:30 ET, then every 3 hrs until 21:00)
┌──────────────────────────────────────────────────────────────┐
│ 1 COLLECT   NWS · NWPS · Open-Meteo · USGS · CO-OPS · CBIBS   │
│             · sun/moon · DNR report · advisories               │
│ 2 FEATURES  pressure trend, fronts, flow vs ceiling, crest,    │
│             temp trends, tide × light, wind × bank             │
│ 3 GATES     safety, flow ceiling, legal, hours → hard stops   │
│ 4 TIERS     candidates ranked Prime/Good/Fair/Poor (hidden)   │
│ 5 JUDGE     Claude API + Forecaster prompt                     │
│ 6 VALIDATE  schema + gate check in code, Validator prompt     │
│             fail twice → code-built fallback card              │
│ 7 PUBLISH   forecast/latest.json + candidates.json            │
└───────────────────────────────┬──────────────────────────────┘
                                │  delivery path picked in Phase 0
┌───────────────────────────────▼──────────────────────────────┐
│ 7 Fish app · Cast screen                                      │
│  Cast   → shows latest forecast instantly, with its age       │
│  Re-cast (chip changed) → page asks Claude (`sample`) using   │
│           stored candidates; page code re-applies gates        │
│  Log trip → trip.rec links back to the forecast               │
└──────────────────────────────────────────────────────────────┘
```

**Delivery path into the app** (Phase 0 tests these in order and keeps the first that works without manual approval):
1. Page reads `latest.json` directly (from GitHub Pages or raw GitHub). Simplest, but the data is public, which would show your spots and schedule. Only if you're fine with that.
2. Page reads it through your GitHub connector (the page's `mcp` capability). Private, no extra moving parts.
3. A Claude scheduled task copies the JSON into the 7 Fish db. Only if it runs unattended with zero approval prompts.

**Freshness handshake.** Every snapshot carries `generated_at`. The card shows its age. Over 3 hours old, a banner says so; over 12 hours, Cast becomes "Run anyway (stale data)". Actions cron can run late, which is why collection starts at 03:30 for a 05:00 decision.

**Failure behavior.** If a source fails, those values go `not_found` and confidence drops, never the fishing quality. If Claude's card fails validation twice, or ever breaks a gate or a regulation, Claude's text is thrown out and code builds a plain card from the top fully-passing candidate, or SKIP.

**Cost.** Actions minutes are well inside the free tier. The Claude API call needs an Anthropic API key in Actions secrets; per-run cost is small but gets confirmed against current pricing in Phase 0. Re-cast runs on your claude.ai plan.

## 4. Data sources (reachability checked Oct 14, 2026)

| Source | What it gives | Window | Key |
|---|---|---|---|
| NWS API (`api.weather.gov`) | Hourly forecast, alerts, marine zones | 7 days ahead | No; User-Agent required |
| NOAA NWPS (river forecasts) | Flood categories, forecast stage and crest for Potomac and Monocacy gauges | Several days ahead | Confirm in Phase 0 |
| Open-Meteo | Hourly pressure, cloud, wind, gusts, rain | 72 hrs back, 16 days ahead | No (non-commercial) |
| USGS Water Data API (`api.waterdata.usgs.gov/ogcapi`) | Discharge, gage height, water temp | Continuous + daily | Confirm in Phase 0 |
| NOAA CO-OPS (`api.tidesandcurrents.noaa.gov`) | Tides, water level, water temp, pressure, wind, current predictions | Up to 1 yr per call | No |
| NOAA CBIBS buoys (`mw.buoybay.noaa.gov/api/v1`) | Bay water temp, salinity, dissolved oxygen, turbidity, waves | Real-time + history | Yes; request free key |
| Sun and moon (computed, `skyfield`) | Phase, illumination, rise/set/transit, sunrise/sunset | Any date | n/a |
| Maryland DNR fishing report (WordPress JSON) | Weekly report text | Weekly | No |
| Advisories (MDE, Eyes on the Bay) | Algae, bacteria, closures | Varies | Find feeds in Phase 0 |
| 7 Fish db | Your trips, spots, firsthand notes | All logged | n/a |

Hard rule: new USGS Water Data API only. Legacy WaterServices is being degraded now and retired in Q1 2027.

Every value carries a label (`measured`, `forecast`, `modeled`, `report`, `reasoning`, `not_found`), source, station, distance from the spot, and timestamp. Open-Meteo's surface temp over water is `modeled` and never shown as water temp. A DNR report rarely dates its catches, so the report's week is used as the latest possible catch date, and anything over 30 days from run time is history.

## 5. Knowledge base (versioned YAML in the repo)

- **species/{key}.yaml**, keyed to the existing Findex keys: water-temp activity bands, seasonal calendar by region, flow / clarity / tide / light preferences, front sensitivity, best shore methods and rigs by condition, regs and consumption-advisory pointers. Claims are tagged `documented` (with a URL actually opened) or `reasoning`; reasoned bands are allowed and labeled.
- **spots/{id}.yaml**, keyed to existing 7 Fish spot ids: coordinates, water type, bank orientation, nearest USGS gauge / NWPS point / CO-OPS station / CBIBS buoy with distance, a **fishable-flow ceiling** set from your own experience (the river is unfishable long before it floods), Presence / Quality / Access each with status and evidence, hours, after-dark status, jurisdiction, crowding, your firsthand notes. FOD known corrections are hard facts here.
- **rules/gates.yaml**: tunable safety and legality thresholds.
- **rules/regs.yaml**: seasons, slots, creel and **targeting closures** (not just harvest) per species and jurisdiction, each with `checked_on`. Tidal Potomac mainstem, DC and Virginia banks get an automatic jurisdiction flag.
- **profile.yaml**: FOD standing profile, trip types, gear, Luca mode.

**v1 scope: 6 spots, 8 species.** Spots: the 6 already in 7 Fish or a swap you choose (Noland's Ferry and Matapeake are the obvious candidates). Species: striped bass, white perch, channel catfish, blue catfish, flathead catfish, northern snakehead, walleye, smallmouth bass (as a baseline read on river conditions). Everything else grows in after the loop is proven.

## 6. Engine logic

1. **Collect** 72 hours back, 7 days forward, per active spot.
2. **Normalize** to ET and US units; missing stays `not_found`.
3. **Features**: 24h pressure change and class (rising / steady / falling / front passing); 72h air and water temp trend; flow vs. the spot's fishable ceiling plus NWPS forecast crest (catches upstream rain that hasn't arrived yet); rain in the last 48h as a clarity proxy, with buoy turbidity where it exists; dissolved oxygen on Bay spots in warm months; tide stage overlapping dawn and dusk; moon phase and transit in the window; wind direction against bank orientation; usable daylight.
4. **Gates** (code, before Claude sees anything): thunderstorms or warnings in the window, forecast flow over the ceiling or any flood category, gusts over the spot's threshold, closures and advisories, posted hours vs. window, targeting or harvest season closed, unverified jurisdiction or license.
5. **Candidates**: spot × species × window rows that pass presence, season and the trip type's drive limit from Frederick.
6. **Tiers** (hidden): Prime / Good / Fair / Poor from documented condition fit. Pressure and moon nudge timing; they never outrank access, water or a fresh report. Claude may move a candidate up one tier at most, and only with a cited report under 30 days old.
7. **Judge**: Forecaster prompt over the top candidates, snapshot, DNR report and your history.
8. **Validate**: schema, gates and regs re-checked in code, then the Validator prompt. One automatic rewrite; second failure or any gate/legal break triggers the code-built fallback card.
9. **Publish** forecast and the compact candidate set with gate results, so Re-cast can enforce the same gates in page code.

## 7. The learning loop

The 7 Fish trip schema already has a `rec` field; **Log this trip** from a forecast fills it automatically. Monthly, or after every 5 logged trips, the Calibration prompt compares forecasts with outcomes and proposes edits to spot and species files. You approve; they're committed with the reason. Firsthand access findings can be adopted on one trip; biology needs more than one. No machine learning before roughly 30 logged trips, and a blank trip is never proof the fish are gone.

## 8. Repo layout

```
7fish/
  README.md
  docs/        PLAN.md  BRAND.md  REVIEW.md  BACKLOG.md
  prompts/     00-build-orchestrator  10-forecaster  20-validator
               30-knowledge-author  40-calibration
  knowledge/   species/  spots/  rules/  profile.yaml
  engine/      collect/  features/  gates/  candidates/  judge/
               schema/  tests/
  app/         Cast screen for the 7 Fish artifact
  .github/workflows/forecast.yml
  brand/       logo master and exports
```

## 9. Build phases

| Phase | Deliverable | Done when |
|---|---|---|
| 0. Spikes (1 day) | Prove the plumbing | Delivery path chosen (tested in order); USGS OGC query returns Monocacy flow + temp; NWPS returns a crest forecast for one Potomac gauge; CBIBS key requested; `sample` works from the 7 Fish page; Claude API key works from Actions with a per-run cost estimate; push notification feasibility known; advisory feeds located |
| 1. Collector + knowledge (parallel) | `snapshot.json` for 6 spots on cron; 8 species and 6 spot files | One week of clean snapshots; every value labeled; fetcher and gate tests pass; you've reviewed each spot file and set its flow ceiling |
| 2. Brain | Gates, tiers, Forecaster, Validator, fallback card | Backtest on 10 past days and your logged trips with zero gate violations and zero invented values |
| 3. Face | Cast screen in 7 Fish | One tap to a card on iPhone; Re-cast under 20 seconds; stale banner and fallback card both demonstrated |
| 4. Loop | Trip linking + Calibration | First calibration reviewed and committed |
| v2 | More spots and species, Solomons, Outer Banks, NC regs, surf | After 30 days of v1 use |

## 10. Risks

- **Data gaps** (gauge offline, buoy pulled for winter): `not found` on the card, lower confidence, never a guessed value.
- **Regulations change**: `checked_on` on every rule; stale rules warn on the card; Knowledge prompt re-checks each season.
- **USGS migration**: new API only, confirmed in Phase 0.
- **Overconfidence**: words not numbers, confidence separate from quality, Validator rejects any score.
- **Late cron**: early collection plus the freshness handshake.
- **Artifact limits**: if `sample` isn't reliable, Re-cast opens a prefilled FOD chat instead.
- **Scope creep**: v1 is 6 spots, 8 species, Maryland only.
