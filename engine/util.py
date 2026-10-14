"""Shared helpers: value objects, time parsing, geometry, unit conversion."""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = timezone.utc
LABELS = ("measured", "forecast", "modeled", "report", "reasoning", "not_found")


def val(v, unit=None, label="measured", src=None, dist_mi=None, at=None, **extra) -> dict:
    """The spec's value object. v None -> label forced to not_found."""
    if v is None:
        label = "not_found"
    if isinstance(v, float):
        v = round(v, 2)
    out = {"v": v, "unit": unit, "label": label, "src": src, "dist_mi": _r(dist_mi, 1), "at": iso(at)}
    out.update(extra)
    return out


def not_found(unit=None, src=None, **extra) -> dict:
    return val(None, unit, "not_found", src, **extra)


def _r(x, n):
    return round(x, n) if isinstance(x, (int, float)) else x


def iso(t):
    if t is None or isinstance(t, str):
        return t
    if t.tzinfo is None:
        t = t.replace(tzinfo=ET)
    return t.astimezone(ET).isoformat(timespec="minutes")


_TZ_SHORT = re.compile(r"([+-]\d{2})$")


def parse_time(s, assume_tz=ET):
    """Parse the time formats the APIs use. Returns aware datetime or None."""
    if s is None:
        return None
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=assume_tz)
    if not isinstance(s, str) or not s.strip():
        return None
    s = s.strip()
    if "/" in s:  # NWS validTime "2026-10-14T10:00:00+00:00/PT1H"
        s = s.split("/", 1)[0]
    s = s.replace("Z", "+00:00")
    s = _TZ_SHORT.sub(r"\1:00", s)
    if len(s) == 16 and s[10] == " ":  # CO-OPS "2026-10-14 03:12"
        s = s.replace(" ", "T")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=assume_tz)
    return dt


def parse_iso_duration_h(s: str) -> float:
    """PT1H, PT3H, P1DT2H -> hours."""
    m = re.match(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?", s or "")
    if not m:
        return 1.0
    d, h, mi = (int(x) if x else 0 for x in m.groups())
    return d * 24 + h + mi / 60 or 1.0


def to_float(x):
    if x is None or isinstance(x, bool):
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or f <= -999:  # NWPS uses -999 for missing
        return None
    return f


def c_to_f(c):
    return None if c is None else c * 9 / 5 + 32


def hpa_to_inhg(h):
    return None if h is None else h * 0.0295299830714


def kmh_to_mph(k):
    return None if k is None else k * 0.621371


def haversine_mi(lat1, lon1, lat2, lon2) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def drive_minutes(lat, lon, origin_lat=39.4143, origin_lon=-77.4105) -> int:
    miles = haversine_mi(origin_lat, origin_lon, lat, lon)
    minutes = miles * 1.25 / 48 * 60
    return int(5 * round(minutes / 5))


CARDINALS = {
    "N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5, "E": 90, "ESE": 112.5, "SE": 135, "SSE": 157.5,
    "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5, "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5,
}


def cardinal_to_deg(s):
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    return CARDINALS.get(str(s).strip().upper())


def deg_to_cardinal(d):
    if d is None:
        return None
    names = list(CARDINALS.keys())
    return names[int(((d % 360) + 11.25) // 22.5) % 16]


def angle_diff(a, b) -> float:
    d = abs((a - b) % 360)
    return min(d, 360 - d)


def circular_mean(degs):
    degs = [d for d in degs if d is not None]
    if not degs:
        return None
    s = sum(math.sin(math.radians(d)) for d in degs)
    c = sum(math.cos(math.radians(d)) for d in degs)
    if abs(s) < 1e-9 and abs(c) < 1e-9:
        return None
    return math.degrees(math.atan2(s, c)) % 360


def fmt_clock(t: datetime) -> str:
    t = t.astimezone(ET)
    h = t.hour % 12 or 12
    return f"{h}:{t.minute:02d}"


def ampm(t: datetime) -> str:
    return "AM" if t.astimezone(ET).hour < 12 else "PM"


def window_text(start: datetime, end: datetime) -> str:
    s, e = start.astimezone(ET), end.astimezone(ET)
    day = s.strftime("%a %b ") + str(s.day) + s.strftime(", %Y")
    if ampm(s) == ampm(e):
        rng = f"{fmt_clock(s)}–{fmt_clock(e)} {ampm(e)}"
    else:
        rng = f"{fmt_clock(s)} {ampm(s)}–{fmt_clock(e)} {ampm(e)}"
    return f"{day} · {rng} ET"


def nearest(series, t, max_gap=timedelta(hours=2)):
    """series: list of (datetime, value). Returns value nearest to t within max_gap."""
    best, bd = None, None
    for ts, v in series:
        if v is None:
            continue
        d = abs((ts - t).total_seconds())
        if bd is None or d < bd:
            best, bd = (ts, v), d
    if best is None or bd > max_gap.total_seconds():
        return None
    return best


def in_range(series, start, end):
    return [(t, v) for t, v in series if start <= t < end and v is not None]
