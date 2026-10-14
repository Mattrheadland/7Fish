# Knowledge file formats

All files are YAML. Every factual claim carries `tag: documented` with `src:` (a URL actually opened) or `tag: reasoning`. Missing facts are the string `not found`, never a guess. Region keys used everywhere:

`frederick-rivers` (Monocacy and small Frederick County rivers), `upper-potomac` (nontidal Potomac, Harpers Ferry to Great Falls), `tidal-potomac` (DC to Point Lookout, incl. tidal tribs like Mattawoman), `upper-bay` (Susquehanna Flats to Bay Bridge), `middle-bay` (Bay Bridge to Choptank/Tilghman), `md-coast` (Ocean City inlet, bays, surf).

Month status words (ordinal, low→high): `closed` (legally closed to targeting) · `absent` · `poor` · `fair` · `good` · `prime`.

## species/<key>.yaml  (key = Findex key)

```yaml
key: striped-bass
name: Striped bass
kid_friendly: false            # simple bait, attainable, for Luca mode
temp_bands_f:                  # water temperature, °F. Contiguous, ordered.
  - {band: inactive, max: 45, tag: reasoning}
  - {band: slow,     min: 45, max: 52, tag: documented, src: "https://..."}
  - {band: active,   min: 52, max: 60, tag: ...}
  - {band: peak,     min: 60, max: 68, tag: ...}
  - {band: active,   min: 68, max: 75, tag: ...}
  - {band: stressed, min: 75, tag: ...}
season:                        # only regions where the species is a realistic shore target
  middle-bay: {1: poor, 2: poor, 3: poor, 4: fair, 5: good, 6: fair, 7: poor, 8: poor, 9: fair, 10: good, 11: prime, 12: good, tag: reasoning, note: "..."}
prefs:                         # effect on the bite: plus | minus | neutral | unknown
  flow:   {rising: plus, falling: neutral, high_muddy: minus, low_clear: minus, tag: ..., note: "..."}
  light:  {dawn: plus, day: minus, dusk: plus, night: plus, overcast: plus, tag: ..., note: "..."}
  tide:   {incoming: plus, outgoing: plus, slack: minus, tag: ..., note: "..."}      # n/a for nontidal-only species → omit
  front:  {pre_front_falling: plus, post_front_high_rising: minus, steady: neutral, tag: ..., note: "..."}
  wind:   {onshore_light: plus, strong: minus, tag: ..., note: "..."}               # optional
methods:                       # best shore methods, in priority order
  - id: cut-bait-bottom
    when: "Moving tide, dawn/dusk, water 55-70°F"
    rig_line: "6/0 circle, 2-3 oz egg sinker on a fish-finder slide, bead, barrel swivel, 24 in 40 lb fluoro, fresh menhaden chunk"
    rig: {hook: "...", weight: "...", leader: "...", hardware: "...", bait_or_lure: "..."}
    switch_to: paddletail-jig
    switch_trigger: "No bites in 30 min with bait being picked clean, or birds working"
    gear_note: "Fits Matt's 7 ft Crossfire inshore combo"   # say when it needs gear Matt lacks
advisory: {url: "...", note: "...", tag: documented}
notes: ["..."]
sources: [{url: "...", title: "...", accessed: 2026-10-14}]
```

## spots/<id>.yaml  (id = 7 Fish spot id)

```yaml
id: point-of-rocks
name: Point of Rocks
status: active                 # active | ruled-out
lat: 39.2738
lon: -77.5376
approx: true
region: upper-potomac
water_type: river              # river | tidal-river | bay | pier | inlet
bank_faces_deg: 180            # compass direction the angler faces toward the water, or null
luca_ok: false                 # clean, easy bank for a young kid
stations:                      # nearest data sources; id null if none within reason
  usgs:  {id: "01638500", name: "Potomac River at Point of Rocks, MD", distance_mi: 0.3, has: [discharge, gage_height, water_temp], tag: documented, src: "..."}
  nwps:  {lid: "PORM2", name: "...", distance_mi: 0.3, tag: documented, src: "..."}
  coops: {id: null}
  cbibs: {id: null}
flow_ceiling: {value: null, unit: cfs, source: ask_matt}
wind_gust_limit_mph: 30        # bank comfort/safety limit, reasoning default
species:                       # only species with some presence evidence
  smallmouth-bass: {presence: verified, quality: not_verified, evidence: [{text: "...", date: "2026-09", tag: documented, src: "..."}]}
access:
  status: not_verified         # verified | not_verified | ruled-out (overall)
  parking: {text: "...", tag: ...}
  walk:    {text: "...", tag: ...}
  stand:   {text: "...", tag: ...}
  casting: {text: "...", tag: ...}
  landing: {text: "...", tag: ...}
  hours:   {text: "...", open: "sunrise", close: "sunset", tag: ...}   # open/close: HH:MM, sunrise, sunset, 24h, or "not found"
  after_dark: not_verified     # allowed | prohibited | not_verified
jurisdiction: {water: nontidal, state: MD, license: "Maryland nontidal license", flags: ["..."], tag: ...}
crowding: "..."
hazards: ["..."]
matt_notes: ["..."]            # verbatim, src Matt
sources: [...]
```

## rules/regs.yaml

```yaml
checked_on: 2026-10-14
species:
  striped-bass:
    - area: "Chesapeake Bay and tidal tributaries (MD)"
      regions: [upper-bay, middle-bay, tidal-potomac]
      harvest: [{start: "05-16", end: "07-15", size: "19-24 in slot", creel: "1 per person per day", note: "..."}]
      targeting_closed: [{start: "04-01", end: "05-15", note: "..."}]
      src: "https://dnr.maryland.gov/..."
      tag: documented
```

`harvest` empty means catch-and-release only. Dates are MM-DD, inclusive. Anything not verified gets `tag: reasoning` plus a `warning:`.

## rules/gates.yaml

Thresholds the engine applies before anything is recommended. All tunable; Matt's numbers beat defaults.
