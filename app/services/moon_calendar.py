"""
Moon calendar computation service.

Extracted from arp_moon_calendar.py. Computes moon phase/separation/risk
for all targets over a date range.
"""

import datetime
import math

import ephem

from arp_common import OBSERVATORIES, moon_risk


def compute_moon_data(targets, days, site_key):
    """
    Compute moon data for all targets over a date range.

    Args:
        targets: list of dicts with keys: id, arp_number, ra_hours, dec_degrees
        days: number of days to compute
        site_key: observatory name

    Returns:
        (rows, metadata) where:
            rows: list of {target_id, night_date, phase_pct, separation_deg, risk}
            metadata: {phase_calendar, next_new_moon, next_full_moon, start_date}
    """
    cfg = OBSERVATORIES[site_key]
    observer = ephem.Observer()
    observer.lat = cfg["lat"]
    observer.lon = cfg["lon"]
    observer.elevation = cfg["elev"]

    today = datetime.date.today()
    utc_hour = (24 - cfg["utc_offset"]) % 24

    phase_calendar = []
    moon_obj = ephem.Moon()
    for d in range(days):
        night = today + datetime.timedelta(days=d)
        observer.date = night.strftime(f"%Y/%m/%d {utc_hour:02d}:00:00")
        moon_obj.compute(observer)
        phase_calendar.append({
            "date": night.isoformat(),
            "phase_pct": round(moon_obj.phase, 1),
        })

    next_new = ephem.Date(
        ephem.next_new_moon(today.strftime("%Y/%m/%d"))
    ).datetime().date()
    next_full = ephem.Date(
        ephem.next_full_moon(today.strftime("%Y/%m/%d"))
    ).datetime().date()

    rows = []
    moon = ephem.Moon()

    for t in targets:
        target = ephem.FixedBody()
        ra_h = t["ra_hours"]
        dec_deg = t["dec_degrees"]

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

        for d in range(days):
            night = today + datetime.timedelta(days=d)
            observer.date = night.strftime(f"%Y/%m/%d {utc_hour:02d}:00:00")
            moon.compute(observer)
            target.compute(observer)

            phase = moon.phase
            sep = math.degrees(ephem.separation(moon, target))

            rows.append({
                "target_id": t["id"],
                "night_date": night,
                "phase_pct": round(phase, 1),
                "separation_deg": round(sep, 1),
                "risk": moon_risk(phase, sep),
            })

    metadata = {
        "phase_calendar": phase_calendar,
        "next_new_moon": next_new,
        "next_full_moon": next_full,
        "start_date": today,
    }

    return rows, metadata
