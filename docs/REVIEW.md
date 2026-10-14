# Peer Review Log

Review of plan v1.0 by an independent reviewer (separate Claude agent with no access to the drafting reasoning), October 14, 2026. Every item and what v1.1 did with it.

## Must fix (all adopted)

| # | Finding | Change in v1.1 |
|---|---|---|
| 1 | The 4:50 AM Claude scheduled task could stall waiting for an approval nobody is awake to give | Judgment moved into GitHub Actions via the Claude API. App delivery path is tested in Phase 0, and the scheduled-task route is accepted only if it runs with zero prompts |
| 2 | Two schedulers, no handshake; Actions cron runs late | Single pipeline. Collection starts 03:30, then every 3 hours. `generated_at` drives a stale banner at 3 hours and a "Run anyway" state at 12 |
| 3 | No flood or river-forecast source; "action stage" gate is a safety line, not a fishability line | NOAA NWPS added for flood category and forecast crest. Per-spot fishable-flow ceiling set from Matt's own experience |
| 4 | Eleven-field card isn't "basic looking" | Card shows verdict, headline, best play and a one-line rig. Everything else sits in one Details sheet |
| 5 | Re-cast bypassed gates and validation | Gate results ship with the candidate set; page code re-applies them before showing any Re-cast card. `sample` gets compact candidates only |
| 6 | "Ship with a warning" after failing validation is unsafe for gate or legal breaks | Any gate or legal break, or a second failure, throws out Claude's text and shows a code-built card from the top fully-passing candidate, or SKIP |

## Should fix (all adopted)

| # | Finding | Change |
|---|---|---|
| 1 | "Now" ran on stale data | Chip renamed "Next 3 hrs" and backed by the 3-hour refresh |
| 2 | Regs only covered harvest | Targeting closures are gates. Automatic jurisdiction flag for tidal Potomac mainstem, DC and Virginia |
| 3 | Forecaster forced exactly three drivers; tier-override rules unclear; GO IF not checkable | "Up to three". Claude can raise a candidate one tier at most, only with a cited report under 30 days old. GO IF conditions must be checkable from the truck |
| 4 | Validator gaps | Added: rule values must come from regs.yaml, time-math and sunrise/sunset consistency, drive time vs. trip type, verdict vs. tier. 30 days measured from run time. Required fields depend on verdict |
| 5 | DNR reports lack catch dates; demanding a source for every temp boundary invites invention | Report week stands in as latest possible catch date. Reasoned bands allowed when labeled `reasoning` |
| 6 | Phase 2 was weeks of work; 10-day pressure history unnecessary; push notifications unverified | v1 cut to 6 spots and 8 species; collector and knowledge built in parallel; 72-hour history; push moved to Phase 0 |

## Confirmed sound (kept)
Gates applied in code before Claude sees anything. Hidden word tiers, no displayed scores. Value labeling, with modeled water temp never shown as water temp. New USGS API only. Wind against bank orientation. Luca mode. Calibration requires Matt's approval and no machine learning before about 30 trips. Slate SKIP and the voice guide. FOD known corrections as hard facts.

## Residual risks I couldn't close on paper
- Whether a claude.ai artifact page can fetch external JSON or call a GitHub connector unattended is untested. Phase 0 decides, and there's a fallback either way.
- NWPS endpoint shape and the USGS OGC collection names need a live query.
- Per-run Claude API cost needs confirming against current pricing.
