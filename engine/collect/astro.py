"""Sun and moon, computed locally with ephem. No network."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import ephem

from ..util import ET, UTC

SRC = "astro"


def _obs(lat, lon, d: date, horizon="-0:34"):
    o = ephem.Observer()
    o.lat, o.lon = str(lat), str(lon)
    o.elevation = 0
    o.pressure = 0
    o.horizon = horizon
    # local noon in UTC as reference
    noon = datetime(d.year, d.month, d.day, 12, tzinfo=ET).astimezone(UTC)
    o.date = ephem.Date(noon.replace(tzinfo=None))
    return o


def _to_et(edate) -> datetime:
    return ephem.Date(edate).datetime().replace(tzinfo=UTC).astimezone(ET)


def phase_name(illum: float, waxing: bool) -> str:
    if illum < 3:
        return "New Moon"
    if illum > 97:
        return "Full Moon"
    if 47 <= illum <= 53:
        return "First Quarter" if waxing else "Last Quarter"
    if illum < 50:
        return "Waxing Crescent" if waxing else "Waning Crescent"
    return "Waxing Gibbous" if waxing else "Waning Gibbous"


def day(lat: float, lon: float, d: date) -> dict:
    out = {"date": d.isoformat()}
    try:
        o = _obs(lat, lon, d)
        sun = ephem.Sun()
        out["sunrise"] = _to_et(o.next_rising(sun, start=_midnight(d)))
        out["sunset"] = _to_et(o.next_setting(sun, start=_midnight(d)))
        oc = _obs(lat, lon, d, horizon="-6")
        out["civil_dawn"] = _to_et(oc.next_rising(sun, start=_midnight(d), use_center=True))
        out["civil_dusk"] = _to_et(oc.next_setting(sun, start=_midnight(d), use_center=True))
    except Exception as e:  # polar cases don't happen in MD, but never crash
        out["error"] = f"sun: {e}"
    try:
        o = _obs(lat, lon, d)
        moon = ephem.Moon()
        start = _midnight(d)
        noon = ephem.Date(datetime(d.year, d.month, d.day, 12, tzinfo=ET).astimezone(UTC).replace(tzinfo=None))
        moon.compute(noon)
        illum = float(moon.phase)
        nxt = ephem.Moon(ephem.Date(noon + 1))
        waxing = float(nxt.phase) > illum
        out["moon_illum_pct"] = round(illum)
        out["moon_phase"] = phase_name(illum, waxing)
        end = _midnight(d + timedelta(days=1))
        for k, fn in (("moonrise", o.next_rising), ("moonset", o.next_setting), ("moon_transit", o.next_transit)):
            try:
                t = fn(moon, start=start)
                out[k] = _to_et(t) if t < end else None
            except Exception:
                out[k] = None
    except Exception as e:
        out["moon_error"] = str(e)
    return out


def _midnight(d: date):
    return ephem.Date(datetime(d.year, d.month, d.day, 0, 0, tzinfo=ET).astimezone(UTC).replace(tzinfo=None))
