# 7Fish runbook

## What runs, and when
| Piece | Where | When | Cost |
|---|---|---|---|
| Data pull, features, gates, tiers, engine cards | GitHub Actions `forecast.yml` | 07:30, 10:30, 13:30, 16:30, 19:30, 22:30 UTC (≈3:30 AM–6:30 PM EDT; an hour earlier in winter EST), plus any push to `engine/`, `knowledge/` or the workflow | Free (public repo) |
| Copy forecast into 7 Fish | Claude scheduled task "7Fish data sync" | 08:10, 11:10, 14:10, 17:10, 20:10, 23:10 UTC | Small, on Matt's plan |
| Claude's judgment | 7 Fish page, Cast button (`sample`) | Only when Matt presses Cast | On Matt's plan; the first press asks permission |

## Where things live
- Live data the app reads: 7 Fish db `forecast/meta|spots|cands|cards`.
- Every cast: 7 Fish db `casts/c<epoch ms>` (request, card, source, data time). Link a logged trip to the cast that sent Matt there via the trip's `rec` field.
- Full engine output: `data/latest.json`; daily archive `data/history/YYYY-MM-DD.json`; source health `data/run_log.json`.

## When something looks wrong
- **Card says data is stale:** check `data/run_log.json` on GitHub (did Actions run?) and the scheduled task's last run in Claude.
- **A source shows `not found`:** `run_log.json` → `sources.<name>.errors` and `.shape`. USGS uses the new Water Data API only; the legacy API is being retired in Q1 2027.
- **Buoy data missing:** add a free CBIBS key as the GitHub secret `CBIBS_KEY` (request at buoybay.noaa.gov/contact-us).
- **A rule changed:** edit `knowledge/rules/regs.yaml` (keep `checked_on` and `src`), push; the next run uses it.

## Tuning (Matt's numbers beat defaults)
- Fishable-flow ceiling per river spot: `knowledge/spots/<id>.yaml` → `flow_ceiling` (currently `ask_matt`, so the engine falls back to NWS action stage).
- Gust limits: `wind_gust_limit_mph` per spot; global defaults in `knowledge/rules/gates.yaml`.
- New spot or species: run `prompts/30-knowledge-author.md` in the FOD Project, add the YAML, push.

## Calibration
Monthly or every 5 logged trips: run `prompts/40-calibration.md` against `casts` and logged trips. Approve edits before they're committed.
