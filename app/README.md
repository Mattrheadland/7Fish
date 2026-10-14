# 7 Fish app (Cast screen)

`7fish-app.html` is the full published page of the 7 Fish artifact (https://claude.ai/artifact/1e3rYSMWGrCPrmeuQpuD2W), including the Cast tab. `cast.js` and `cast.css` are the Cast source, spliced into the page before `function boot()` and before the main style block's closing tag.

Capabilities: `assets`, `db`, `sample`.

Database collections the Cast screen uses:
- `forecast/meta|spots|cands|cards` — written by the "7Fish data sync" scheduled task from `data/app/*.json` (each < 240 KB; the db caps a document at 256 KB). The page merges them only when all four share one `generated_at`.
- `casts/c<epoch ms>` — every Cast result: request, card, source (claude or engine), data timestamp. Used to replay a cast for the same data and settings, and later for calibration against logged trips.

Flow on Cast: filter passing candidates for the chosen slot → send the Forecaster rules plus a compact data slice to Claude through `sample.json` → check the card in code (verdict, play must be a passing candidate, Luca rules, no probabilities) → on any failure, show the engine card built on the phone instead.
