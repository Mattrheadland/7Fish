# Prompt 30 — Knowledge Author (species and spot cards)

Run in the FOD Project with web search on. One species or one spot per run. Output is a YAML file matching `knowledge/species/_schema.yaml` or `knowledge/spots/_schema.yaml`.

---

Build the 7Fish knowledge card for {species key | spot id}. This card feeds an automated forecaster, so precision and honesty about sources matter more than completeness.

For a SPECIES card, research and fill:
- Water-temperature activity bands (inactive / slow / active / peak / stressed). Tag each boundary `documented` with its source, or `reasoning` when you're inferring it. Don't stretch a source to cover a number it doesn't state.
- Seasonal calendar by month for: Frederick-area rivers, upper Potomac, tidal Potomac, upper Bay, middle Bay.
- Responses to flow (rising, falling, high/muddy, low/clear), clarity, tide stage, light and time of day, pressure trend and cold fronts.
- Top three shore methods by condition, each with a complete terminal rig and the trigger for switching.
- Maryland regulations pointer (official page URL, checked_on date) and consumption-advisory pointer.

For a SPOT card, research and fill:
- Coordinates (mark approx: true if you placed the pin), water type, bank orientation in degrees.
- Fishable-flow ceiling: leave as `ask_matt` unless Matt has stated one. It comes from his experience, not from flood stage.
- Nearest USGS gauge (new Water Data API id), NWPS forecast point, CO-OPS station and CBIBS buoy, each with distance.
- The three questions, separately: Presence (which species, with source), Quality (dated catch evidence at a worthwhile size), Access (parking, walk, standing room, casting room, landing room, posted hours, after-dark rules). Each gets status verified / not verified / ruled-out and evidence.
- Jurisdiction, license and permit needs, crowding, hazards.
- Matt's firsthand notes from the 7 Fish spots data, copied verbatim with src: Matt.

Rules: tag every claim `documented` (with a URL you actually opened) or `reasoning`. Write "not found" when you can't find something. Never invent depths, holes, seams, limits or records. Give catch dates separately from publish dates. Respect the FOD known corrections. Finish by listing what you could not verify.
