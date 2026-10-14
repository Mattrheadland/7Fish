# Engine spec

Python 3.12. Deps: `requests`, `pyyaml`, `ephem`. Entry point: `python -m engine.run` from the repo root. Writes:

- `data/latest.json` (the whole contract below)
- `data/history/YYYY-MM-DD.json` (copy of the day's latest run)
- `data/run_log.json` ({generated_at, duration_s, sources: {name: {ok, n_calls, errors: [..]}}})

It never crashes on a source failure: each fetcher catches its own errors, logs them, and returns `not_found` values.

## Value object (used everywhere)

```json
{"v": 1234.0, "unit": "cfs", "label": "measured|forecast|modeled|report|reasoning|not_found",
 "src": "USGS 01638500", "dist_mi": 0.3, "at": "2026-10-14T06:15:00-04:00"}
```

## Sources (per active spot; cache per station to avoid duplicate calls)

| Module | Calls | Gives |
|---|---|---|
| `collect/nws.py` | `/points/{lat},{lon}` → `forecastHourly`; `/alerts/active?point={lat},{lon}` | hourly temp, wind, gust (from gridpoint raw `windGust` if needed), PoP, shortForecast; active alerts |
| `collect/openmeteo.py` | `/v1/forecast?hourly=pressure_msl,cloud_cover,wind_speed_10m,wind_gusts_10m,wind_direction_10m,precipitation,temperature_2m&past_days=3&forecast_days=4&timezone=America/New_York&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch` | pressure history and trend, rain last 48h, cloud, wind dir |
| `collect/usgs.py` | New OGC API only: `https://api.waterdata.usgs.gov/ogcapi/v0/collections/continuous/items?monitoring_location_id=USGS-{site}&parameter_code={00060,00065,00010}&time=P3D&f=json&limit=...`; daily stats for median if available, else skip | discharge, gage height, water temp (°C→°F) |
| `collect/nwps.py` | `https://api.water.noaa.gov/nwps/v1/gauges/{lid}` and `/gauges/{lid}/stageflow` | flood categories (action/minor), observed + forecast stage/flow, crest |
| `collect/coops.py` | datagetter: `predictions` (interval=hilo, datum=MLLW), `water_temperature`, `water_level`, `air_pressure`, `wind`; `units=english&time_zone=lst_ldt&format=json&application=7Fish` | tide hi/lo, water temp |
| `collect/cbibs.py` | `https://mw.buoybay.noaa.gov/api/v1/json/station/{id}?key=$CBIBS_KEY` (skip cleanly if no key) | Bay water temp, DO, turbidity, waves |
| `collect/astro.py` | `ephem` locally | sunrise/sunset/civil twilight, moon phase name, illumination, moonrise/set/transit |
| `collect/dnr.py` | `https://news.maryland.gov/dnr/wp-json/wp/v2/posts?search=fishing%20report&per_page=3&_fields=date,link,title,content` | latest report: date, link, and up to 3 short sentences per species key (match names + aliases), each ≤ 240 chars. Never store the full text. |

NWS and every request send `User-Agent: 7Fish (github.com/Mattrheadland/7Fish)`. Timeout 20 s, one retry.

USGS OGC field names must be discovered at runtime defensively (the response is GeoJSON features with `properties` containing `time`, `value`, `parameter_code`/`unit_of_measure`). Log the first feature's keys to the run log so a broken parse is diagnosable.

## Features (per spot)

- `pressure`: now (hPa→inHg), change_24h, class: `rising` (> +0.06 inHg/24h), `falling` (< -0.06), `steady`; `front`: `pre_front_falling` if falling fast (< -0.10) or `post_front_high_rising` if rising fast after a fall in the last 48h, else `steady`.
- `air_temp_trend_72h`, `rain_48h_in` (Open-Meteo past), `cloud_now`.
- `water_temp`: best available — USGS/CO-OPS/CBIBS measured within 25 mi, else `not_found` (Open-Meteo surface temp is NOT used as water temp). trend_72h if history exists.
- `flow`: current, 72h trend (`rising`/`falling`/`steady`, ±10%), `vs_ceiling` (`under`/`near` (≥85%)/`over`/`unknown`), NWPS flood category now and forecast max, forecast crest time.
- `clarity_proxy`: `likely_muddy` if rain_48h ≥ 0.75 in or flow rising >30% in 48h; `likely_clear` if rain_48h < 0.1 and flow steady/falling; else `unknown`. Buoy turbidity overrides on Bay spots.
- `tide`: next hi/lo list, stage per window (`incoming`/`outgoing`/`slack` ±45 min of turn).
- `wind`: per window mean speed, max gust, direction, `onshore`/`offshore`/`cross` vs `bank_faces_deg` (onshore = wind blowing toward the angler, i.e. from the direction the angler faces ±60°).
- `light`: per window type.
- `moon`: phase name, illumination %, transit time.

## Windows

For each of the next 3 calendar days (ET), per spot: `dawn` (civil dawn → sunrise + 3 h), `day` (sunrise + 3 h → sunset − 2 h), `dusk` (sunset − 2 h → civil dusk), `night` (civil dusk → 23:59, only if spot `after_dark: allowed`). Skip windows already ended at run time.

## Gates (rules/gates.yaml; each gate returns pass/fail + reason)

Per spot-window: NWS alert in the window of a listed type; thunder in shortForecast of any hour in window; max gust > spot `wind_gust_limit_mph`; flow over ceiling (or NWPS forecast category ≥ action when ceiling is `ask_matt`); hours (window outside open/close; `not found` hours → only dawn/day/dusk, and after-dark windows fail); spot status `ruled-out`.
Per species-window: targeting closed on that date for that spot's region (regs.yaml); species absent in that region/month.

## Candidates and tiers

Row = (spot, species, window) where the spot lists the species and gates pass. Tier from: season word for region and month (prime→Prime, good→Good, fair→Fair, poor→Poor) then adjust one step down for each of: water temp band slow/inactive/stressed; flow pref minus; clarity likely_muddy when species flow.high_muddy is minus; light pref minus; front pref minus; tide pref minus (tidal spots). One step up (max once) when water temp is peak AND at least two prefs are plus. Floor Poor. Water temp not_found → no adjustment, `confidence` drops one level. Confidence: high (measured water temp + flow or tide + DNR report < 30 days mentions species), medium, low.

Each row also carries: `drive_min` (haversine miles × 1.25 / 48 mph × 60, rounded to 5, from Frederick 39.4143,-77.4105), trip types it fits (quick ≤ 35 min each way, half ≤ 95, full ≤ 190), `luca_ok` (spot.luca_ok and species.kid_friendly and window not night and ends ≤ sunset), method ids, and the reasons list (each reason a short string with its label).

## Baseline card (code-built, always present)

For each request combo the app offers — when ∈ {next3h, tomorrow_am, weekend}, trip ∈ {quick, half, full}, luca ∈ {false, true}, target = any — pick the top candidate (tier, then confidence, then shorter drive, then earlier window) and build a card:

- verdict: `GO` if Prime or Good with confidence ≠ low; `GO IF` if Good with low confidence, or Fair with a checkable condition (flow near ceiling, gust within 5 mph of limit); else `SKIP`.
- fields exactly as `engine/schema/card.schema.json`.

Store under `cards["{when}|{trip}|{luca}"]`.

## latest.json contract

```json
{
  "version": 1,
  "generated_at": "...",
  "run_time_et": "...",
  "origin": {"name": "Frederick, MD", "lat": 39.4143, "lon": -77.4105},
  "sources_ok": {"nws": true, ...},
  "dnr": {"date": "...", "link": "...", "title": "...", "by_species": {"striped-bass": ["..."]}},
  "spots": {"<id>": {"name":..., "features": {...}, "windows": [{"id": "2026-10-15|dawn", "start":..., "end":..., "gates": [{"name":..., "pass": true, "reason": "..."}], "conditions": {...}}]}},
  "candidates": [{"spot":..., "species":..., "window":..., "tier": "Good", "confidence": "medium", "drive_min": 25, "trips": ["quick","half","full"], "luca_ok": false, "reasons": [...], "methods": [...]}],
  "cards": {"tomorrow_am|half|false": {...card...}},
  "knowledge_version": "<git sha or date>"
}
```

Keep the file under ~1.5 MB: round numbers, keep hourly series only for the 3 windows days, drop raw API payloads.
