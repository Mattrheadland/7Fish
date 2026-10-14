# Prompt 00 — Build Orchestrator

Paste into a Claude session attached to the 7fish repo to execute one phase. Replace {N}.

---

You're building 7Fish Phase {N} from `docs/PLAN.md`. Read PLAN.md, BRAND.md, REVIEW.md and the prompts folder first. The plan is the spec; if something in it is wrong or impossible, stop and say what and why before changing course.

Ground rules:
- Build only what Phase {N} lists. Note anything else in `docs/BACKLOG.md`.
- Python 3.12 for the engine, plain HTML/JS for the app screen, no framework unless the plan names one.
- Every external value carries {value, unit, label, source, station_id, distance_mi, observed_at}. Missing data is `null` with label `not_found`, never a default.
- USGS: new Water Data API only. Never call waterservices.usgs.gov.
- NWS requests send a User-Agent identifying 7Fish.
- No secrets in the repo; keys go in GitHub Actions secrets.
- Tests for every fetcher (recorded fixtures) and every gate.
- Finish the phase by checking its "Done when" criteria one by one, with evidence, and list what's left.

Report back in under 15 lines: what was built, what passed, what didn't, and the next decision Matt needs to make.
