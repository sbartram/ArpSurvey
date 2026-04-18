"""
Astronomy service — wraps ephem for dark window, visibility, and moon calculations.

All public functions return Python datetime objects (UTC). ephem.Date conversions
are handled internally.
"""

import datetime
import math

import ephem

from arp_common import OBSERVATORIES, moon_risk as _moon_risk


def build_observer(site_key, date):
    """Build a configured ephem.Observer for a site and date."""
    cfg = OBSERVATORIES[site_key]
    observer = ephem.Observer()
    observer.lat = cfg["lat"]
    observer.lon = cfg["lon"]
    observer.elevation = cfg["elev"]
    observer.horizon = "-18"

    utc_noon = (12 - cfg["utc_offset"]) % 24
    observer.date = date.strftime(f"%Y/%m/%d {utc_noon:02d}:00:00")
    return observer


def _ephem_to_datetime(ephem_date):
    """Convert ephem.Date float to a timezone-aware UTC datetime."""
    return ephem.Date(ephem_date).datetime().replace(tzinfo=datetime.timezone.utc)


def dark_window(site_key, date):
    """
    Compute astronomical twilight boundaries for a given site and date.
    Returns (evening_twilight, morning_twilight) as UTC datetimes.
    """
    observer = build_observer(site_key, date)
    sun = ephem.Sun()

    eve_twi = observer.next_setting(sun, use_center=True)
    observer.date = eve_twi
    morn_twi = observer.next_rising(sun, use_center=True)

    return _ephem_to_datetime(eve_twi), _ephem_to_datetime(morn_twi)


def _make_fixed_body(ra_h, dec_deg):
    """Create an ephem.FixedBody from decimal hours RA and decimal degrees Dec."""
    target = ephem.FixedBody()
    h = int(ra_h)
    m = int((ra_h - h) * 60)
    s = ((ra_h - h) * 60 - m) * 60
    target._ra = f"{h:02d}:{m:02d}:{s:05.2f}"

    sign = "-" if dec_deg < 0 else "+"
    ad = abs(dec_deg)
    dd = int(ad)
    dm = int((ad - dd) * 60)
    ds = ((ad - dd) * 60 - dm) * 60
    target._dec = f"{sign}{dd:02d}:{dm:02d}:{ds:04.1f}"
    return target


def target_visibility(ra_h, dec_deg, site_key, eve_dt, morn_dt):
    """
    Compute observable window for a target during the dark window.

    Args:
        ra_h: Right ascension in decimal hours
        dec_deg: Declination in decimal degrees
        site_key: Observatory name
        eve_dt: Evening twilight (UTC datetime)
        morn_dt: Morning twilight (UTC datetime)

    Returns dict with {rise, set, transit, hours} as datetimes/float,
    or None if not observable.
    """
    cfg = OBSERVATORIES[site_key]
    observer = ephem.Observer()
    observer.lat = cfg["lat"]
    observer.lon = cfg["lon"]
    observer.elevation = cfg["elev"]
    observer.horizon = str(cfg["min_el"])

    target = _make_fixed_body(ra_h, dec_deg)

    eve_twi = ephem.Date(eve_dt)
    morn_twi = ephem.Date(morn_dt)

    observer.date = eve_twi
    target.compute(observer)
    alt_eve = math.degrees(target.alt)

    observer.date = morn_twi
    target.compute(observer)
    alt_morn = math.degrees(target.alt)

    if alt_eve >= cfg["min_el"]:
        obs_start = eve_twi
    else:
        observer.date = eve_twi
        try:
            rise = float(observer.next_rising(target))
            obs_start = rise if rise < morn_twi else None
        except ephem.AlwaysUpError:
            obs_start = eve_twi
        except ephem.NeverUpError:
            return None

    if obs_start is None:
        return None

    if alt_morn >= cfg["min_el"]:
        obs_end = morn_twi
    else:
        observer.date = obs_start
        try:
            sett = float(observer.next_setting(target))
            obs_end = min(sett, float(morn_twi))
        except ephem.AlwaysUpError:
            obs_end = float(morn_twi)
        except ephem.NeverUpError:
            obs_end = float(obs_start)

    if obs_end <= obs_start:
        return None

    obs_hrs = (obs_end - float(obs_start)) * 24

    observer.date = obs_start
    try:
        trans = float(observer.next_transit(target))
        if trans > float(morn_twi):
            trans = (float(obs_start) + obs_end) / 2
    except Exception:
        trans = (float(obs_start) + obs_end) / 2

    return {
        "rise": _ephem_to_datetime(obs_start),
        "set": _ephem_to_datetime(obs_end),
        "transit": _ephem_to_datetime(trans),
        "hours": round(obs_hrs, 1),
    }


def alt_at_time(ra_h, dec_deg, site_key, dt):
    """Return altitude in degrees at a specific UTC datetime."""
    cfg = OBSERVATORIES[site_key]
    observer = ephem.Observer()
    observer.lat = cfg["lat"]
    observer.lon = cfg["lon"]
    observer.elevation = cfg["elev"]
    observer.date = ephem.Date(dt)

    target = _make_fixed_body(ra_h, dec_deg)
    target.compute(observer)
    return math.degrees(target.alt)


def moon_info(ra_h, dec_deg, observer):
    """
    Compute moon phase, separation, and risk for a target.

    Args:
        ra_h: RA in decimal hours
        dec_deg: Dec in decimal degrees
        observer: configured ephem.Observer (with date set)

    Returns dict: {phase_pct, separation_deg, risk}
    """
    moon = ephem.Moon()
    target = _make_fixed_body(ra_h, dec_deg)

    moon.compute(observer)
    target.compute(observer)

    phase = moon.phase
    sep = math.degrees(ephem.separation(moon, target))
    risk = _moon_risk(phase, sep)

    return {
        "phase_pct": round(phase, 1),
        "separation_deg": round(sep, 1),
        "risk": risk,
    }
