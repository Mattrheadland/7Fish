"""Generate synthetic API fixtures (shapes from the public API docs) for a fixed run time.

    python tests/fixtures/make_api_fixtures.py

Run time: 2026-10-14 05:00 ET (Wed). Writes tests/fixtures/api/<source>/<kind>.json.
Values are invented test data, not observations.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 14, 5, 0, tzinfo=ET)
OUT = Path(__file__).parent / "api"


def w(source, kind, data):
    p = OUT / source / f"{kind}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1))


def utc(t):
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def nws():
    w("nws", "points", {
        "@context": [], "id": "https://api.weather.gov/points/39.38,-77.4", "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-77.4, 39.38]},
        "properties": {
            "gridId": "LWX", "gridX": 80, "gridY": 75,
            "forecast": "https://api.weather.gov/gridpoints/LWX/80,75/forecast",
            "forecastHourly": "https://api.weather.gov/gridpoints/LWX/80,75/forecast/hourly",
            "forecastGridData": "https://api.weather.gov/gridpoints/LWX/80,75",
            "timeZone": "America/New_York",
        }})
    periods = []
    for i in range(96):
        t = NOW + timedelta(hours=i)
        short = "Mostly Clear" if t.hour < 7 or t.hour > 19 else "Sunny"
        if t.date().day == 16 and 13 <= t.hour <= 18:
            short = "Chance Showers And Thunderstorms"
        periods.append({
            "number": i + 1, "name": "", "startTime": t.isoformat(), "endTime": (t + timedelta(hours=1)).isoformat(),
            "isDaytime": 7 <= t.hour < 19, "temperature": 52 + (8 if 11 <= t.hour <= 17 else 0),
            "temperatureUnit": "F", "temperatureTrend": None,
            "probabilityOfPrecipitation": {"unitCode": "wmoUnit:percent", "value": 40 if "Thunder" in short else 5},
            "dewpoint": {"unitCode": "wmoUnit:degC", "value": 8.3},
            "relativeHumidity": {"unitCode": "wmoUnit:percent", "value": 70},
            "windSpeed": "5 to 10 mph", "windDirection": "W",
            "icon": "", "shortForecast": short, "detailedForecast": "",
        })
    w("nws", "hourly", {"type": "Feature", "properties": {
        "units": "us", "forecastGenerator": "HourlyForecastGenerator", "generatedAt": utc(NOW),
        "updateTime": utc(NOW), "periods": periods}})
    gusts = []
    for i in range(0, 96, 2):
        t = NOW + timedelta(hours=i)
        gusts.append({"validTime": utc(t) + "/PT2H", "value": 24.1})
    w("nws", "grid", {"type": "Feature", "properties": {
        "updateTime": utc(NOW), "windGust": {"uom": "wmoUnit:km_h-1", "values": gusts}}})
    w("nws", "alerts", {"@context": [], "type": "FeatureCollection", "features": [
        {"id": "urn:oid:test.1", "type": "Feature", "geometry": None, "properties": {
            "id": "urn:oid:test.1", "areaDesc": "Frederick", "sent": utc(NOW), "effective": utc(NOW),
            "onset": utc(NOW), "expires": utc(NOW + timedelta(hours=12)), "ends": utc(NOW + timedelta(hours=12)),
            "status": "Actual", "messageType": "Alert", "category": "Met", "severity": "Minor",
            "event": "Heat Advisory", "headline": "Heat Advisory (test fixture)"}}],
        "title": "Current watches, warnings, and advisories"})


def openmeteo():
    start = datetime(2026, 10, 11, 0, 0, tzinfo=ET)
    times, pres, cloud, ws, wg, wd, pr, tmp = [], [], [], [], [], [], [], []
    for i in range(24 * 7):
        t = start + timedelta(hours=i)
        times.append(t.strftime("%Y-%m-%dT%H:%M"))
        # steady pressure, then a falling trend after the run time (pre-front on Oct 15-16)
        hrs_after = (t - NOW).total_seconds() / 3600
        p = 1020.0 + 0.3 * math.sin(i / 6)
        if hrs_after > 0:
            p -= min(hrs_after, 40) * 0.12
        pres.append(round(p, 1))
        cloud.append(30)
        ws.append(7.0)
        wg.append(14.0)
        wd.append(270)
        pr.append(0.0)
        tmp.append(55.0)
    w("openmeteo", "forecast", {
        "latitude": 39.38, "longitude": -77.4, "generationtime_ms": 0.5, "utc_offset_seconds": -14400,
        "timezone": "America/New_York", "timezone_abbreviation": "GMT-4", "elevation": 90.0,
        "hourly_units": {"time": "iso8601", "pressure_msl": "hPa", "cloud_cover": "%", "wind_speed_10m": "mp/h",
                         "wind_gusts_10m": "mp/h", "wind_direction_10m": "°", "precipitation": "inch",
                         "temperature_2m": "°F"},
        "hourly": {"time": times, "pressure_msl": pres, "cloud_cover": cloud, "wind_speed_10m": ws,
                   "wind_gusts_10m": wg, "wind_direction_10m": wd, "precipitation": pr, "temperature_2m": tmp}})


def usgs():
    def coll(pc, unit, fn):
        feats = []
        t = NOW - timedelta(days=3)
        i = 0
        while t <= NOW:
            feats.append({"type": "Feature", "id": f"test-{pc}-{i}",
                          "geometry": {"type": "Point", "coordinates": [-77.3708, 39.3876]},
                          "properties": {"id": f"test-{pc}-{i}", "time_series_id": "abc",
                                         "monitoring_location_id": "USGS-01643000", "parameter_code": pc,
                                         "statistic_id": "00011", "time": utc(t), "value": f"{fn(i):.2f}",
                                         "unit_of_measure": unit, "approval_status": "Provisional",
                                         "qualifier": None, "last_modified": utc(NOW)}})
            t += timedelta(minutes=60)
            i += 1
        return {"type": "FeatureCollection", "features": feats, "numberReturned": len(feats),
                "links": [{"rel": "self", "type": "application/geo+json", "href": "https://api.waterdata.usgs.gov/..."}],
                "timeStamp": utc(NOW)}
    w("usgs", "discharge", coll("00060", "ft^3/s", lambda i: 1700 - i * 3))     # slowly falling
    w("usgs", "gage_height", coll("00065", "ft", lambda i: 3.4 - i * 0.004))
    w("usgs", "water_temp", coll("00010", "degC", lambda i: 15.5 + (i % 24) * 0.02))  # ~60 °F


def nwps():
    w("nwps", "gauge", {
        "lid": "TEST1", "usgsId": "01643000", "reachId": "0", "name": "Test River near Frederick",
        "latitude": 39.3876, "longitude": -77.3708, "rfc": {"abbreviation": "MARFC"},
        "flood": {"stageUnits": "ft", "flowUnits": "kcfs",
                  "categories": {"action": {"stage": 10.0, "flow": -9999}, "minor": {"stage": 15.0, "flow": -9999},
                                 "moderate": {"stage": 20.0, "flow": -9999}, "major": {"stage": 25.0, "flow": -9999}}},
        "status": {"observed": {"primary": 3.1, "primaryUnit": "ft", "secondary": 1.49, "secondaryUnit": "kcfs",
                                "floodCategory": "no_flooding", "validTime": utc(NOW)},
                   "forecast": {"primary": 3.0, "primaryUnit": "ft", "secondary": 1.4, "secondaryUnit": "kcfs",
                                "floodCategory": "no_flooding", "validTime": utc(NOW + timedelta(hours=6))}}})
    obs = [{"validTime": utc(NOW - timedelta(hours=h)), "generatedTime": utc(NOW),
            "primary": round(3.1 + h * 0.003, 2), "secondary": round(1.49 + h * 0.003, 3)} for h in range(72, -1, -6)]
    fc = [{"validTime": utc(NOW + timedelta(hours=h)), "generatedTime": utc(NOW),
           "primary": round(3.1 - h * 0.002, 2), "secondary": round(1.49 - h * 0.002, 3)} for h in range(0, 97, 6)]
    w("nwps", "stageflow", {
        "observed": {"issuedTime": utc(NOW), "wfo": "LWX", "timeZone": "EST5EDT", "primaryName": "Stage",
                     "primaryUnits": "ft", "secondaryName": "Flow", "secondaryUnits": "kcfs", "data": obs},
        "forecast": {"issuedTime": utc(NOW), "wfo": "LWX", "timeZone": "EST5EDT", "primaryName": "Stage",
                     "primaryUnits": "ft", "secondaryName": "Flow", "secondaryUnits": "kcfs", "data": fc}})


def coops():
    meta = {"id": "8575512", "name": "Annapolis", "lat": "38.9833", "lon": "-76.4816"}
    preds = []
    t = datetime(2026, 10, 13, 2, 10, tzinfo=ET)
    typ = "H"
    while t < datetime(2026, 10, 19, tzinfo=ET):
        preds.append({"t": t.strftime("%Y-%m-%d %H:%M"), "v": "1.612" if typ == "H" else "0.402", "type": typ})
        typ = "L" if typ == "H" else "H"
        t += timedelta(hours=6, minutes=12)
    w("coops", "predictions", {"predictions": preds})

    def recent(fn):
        rows = []
        t = NOW - timedelta(hours=72)
        while t <= NOW:
            rows.append(fn(t))
            t += timedelta(minutes=60)
        return rows
    w("coops", "water_temperature", {"metadata": meta, "data": recent(
        lambda t: {"t": t.strftime("%Y-%m-%d %H:%M"), "v": "64.2", "f": "0,0,0"})})
    w("coops", "water_level", {"metadata": meta, "data": recent(
        lambda t: {"t": t.strftime("%Y-%m-%d %H:%M"), "v": "1.023", "s": "0.003", "f": "0,0,0,0", "q": "p"})})
    w("coops", "air_pressure", {"metadata": meta, "data": recent(
        lambda t: {"t": t.strftime("%Y-%m-%d %H:%M"), "v": "1019.8", "f": "0,0,0"})})
    w("coops", "wind", {"metadata": meta, "data": recent(
        lambda t: {"t": t.strftime("%Y-%m-%d %H:%M"), "s": "6.80", "d": "270.00", "dr": "W", "g": "9.70", "f": "0,0"})})


def cbibs():
    w("cbibs", "station", {"stations": [{
        "stationShortName": "AN", "stationLongName": "Annapolis", "active": True,
        "latitude": 38.963, "longitude": -76.448,
        "variable": [
            {"reportName": "Water Temperature", "actualName": "sea_water_temperature", "interval": 600,
             "units": "C", "group": "Water Quality", "elevation": "-0.5",
             "measurements": [{"time": utc(NOW - timedelta(minutes=20)), "value": 17.9, "QA": "GOOD Value"}]},
            {"reportName": "Turbidity", "actualName": "simple_turbidity", "interval": "600",
             "units": "NTU", "group": "Water Quality", "elevation": "-0.5",
             "measurements": [{"time": utc(NOW - timedelta(minutes=20)), "value": "4.1", "QA": "GOOD Value"}]},
            {"reportName": "Air Temperature", "actualName": "air_temperature", "interval": 600,
             "units": "C", "group": "Meteorological", "elevation": "3.0",
             "measurements": [{"time": utc(NOW - timedelta(minutes=20)), "value": 12.0, "QA": "N/A"}]},
        ]}]})


def dnr():
    body = ("<p>Welcome to the report. Anglers fishing the middle Bay are finding Striped bass "
            "along channel edges at dawn, with most fish under the slot. Water temperatures are falling. "
            "In the rivers, test catfish are biting cut bait below the riffles. "
            "Rockfish are also chasing bait near Bay Bridge pilings. Smallmouth bass are holding deep. "
            "Fisheries staff remind anglers to check regulations.</p>")
    w("dnr", "posts", [
        {"date": "2026-10-08T12:00:00", "link": "https://news.maryland.gov/dnr/2026/10/08/maryland-fishing-report-test/",
         "title": {"rendered": "Maryland Fishing Report &#8211; October 8"}, "content": {"rendered": body, "protected": False}},
        {"date": "2026-10-01T12:00:00", "link": "https://news.maryland.gov/dnr/2026/10/01/maryland-fishing-report-old/",
         "title": {"rendered": "Maryland Fishing Report &#8211; October 1"}, "content": {"rendered": "<p>Old.</p>", "protected": False}},
    ])


if __name__ == "__main__":
    nws(); openmeteo(); usgs(); nwps(); coops(); cbibs(); dnr()
    print("fixtures written to", OUT)
