"""
Session planner service.

Extracted from arp_session_planner.py. Computes which targets are observable
on a given night, applies moon avoidance, sorts by transit time.
"""

import datetime

import ephem

from arp_common import OBSERVATORIES, SITE_MAP

from app.services.astronomy import (
    build_observer, dark_window, target_visibility, moon_info, alt_at_time,
)


def compute_session(date, site_key, targets, min_hours, moon_filter):
    """
    Compute observable targets for a given night.

    Args:
        date: observation date (datetime.date)
        site_key: observatory name (e.g. "New Mexico")
        targets: list of dicts with keys: arp_number, name, ra_hours, dec_degrees,
                 size_arcmin, filter_strategy, best_site
        min_hours: minimum observable hours
        moon_filter: "" (all), "GM" (good+marginal), "G" (good only)

    Returns list of observable target dicts sorted by transit time.
    """
    cfg = OBSERVATORIES[site_key]
    eve_dt, morn_dt = dark_window(site_key, date)

    results = []
    for t in targets:
        best_site = t.get("best_site", "Any site") or "Any site"
        compatible = SITE_MAP.get(best_site, ["New Mexico"])
        if site_key not in compatible:
            continue

        ra_h = t["ra_hours"]
        dec_deg = t["dec_degrees"]

        vis = target_visibility(ra_h, dec_deg, site_key, eve_dt, morn_dt)
        if not vis or vis["hours"] < min_hours:
            continue

        obs = build_observer(site_key, date)
        obs.date = ephem.Date(vis["transit"])
        mi = moon_info(ra_h, dec_deg, obs)

        if moon_filter == "G" and mi["risk"] != "G":
            continue
        if moon_filter == "GM" and mi["risk"] == "A":
            continue

        utc_offset = cfg["utc_offset"]

        # Peak elevation at transit
        peak_el = round(alt_at_time(ra_h, dec_deg, site_key, vis["transit"]), 1)

        results.append({
            "arp": t["arp_number"],
            "name": t["name"],
            "ra_hours": ra_h,
            "dec_degrees": dec_deg,
            "size_arcmin": t.get("size_arcmin"),
            "filter_strategy": t.get("filter_strategy", "Luminance"),
            "hours": vis["hours"],
            "peak_elevation": peak_el,
            "rise": vis["rise"].isoformat(),
            "set": vis["set"].isoformat(),
            "transit": vis["transit"].isoformat(),
            "start_local": _utc_to_local_str(vis["rise"], utc_offset),
            "end_local": _utc_to_local_str(vis["set"], utc_offset),
            "transit_local": _utc_to_local_str(vis["transit"], utc_offset),
            "moon": mi,
        })

    results.sort(key=lambda r: r["transit"])
    return results


def _utc_to_local_str(utc_dt, utc_offset):
    """Convert UTC datetime to local HH:MM string."""
    local = utc_dt + datetime.timedelta(hours=utc_offset)
    return local.strftime("%H:%M")
