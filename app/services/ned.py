"""
NED coordinate fetching service.

Extracted from arp_ned_coords.py. Provides NED lookups with rate limiting.
"""

import re
import time

try:
    from astroquery.ipac.ned import Ned
    from astroquery.exceptions import RemoteServiceError
    HAS_ASTROQUERY = True
except ImportError:
    HAS_ASTROQUERY = False

from arp_common import parse_catalog_coords


def ned_query_names(raw_name, arp_num):
    """Return list of names to try querying NED with, in priority order."""
    name = raw_name.strip()
    primary = re.split(r'\s*\+\s*', name)[0].strip()
    primary = re.sub(r'\s+(comp|A|B|C)$', '', primary, flags=re.IGNORECASE).strip()

    candidates = [primary]
    if name != primary:
        candidates.append(name)
    candidates.append(f"Arp {arp_num}")

    seen = set()
    return [c for c in candidates if not (c in seen or seen.add(c))]


def fetch_ned_coords(arp_number, name, fallback_ra_deg=0.0, fallback_dec=0.0):
    """
    Query NED for a single target's coordinates.
    Returns dict: {ra_hours, dec_degrees, ned_name, source}
    """
    if not HAS_ASTROQUERY:
        return {"ra_hours": fallback_ra_deg / 15.0, "dec_degrees": fallback_dec,
                "ned_name": "", "source": "catalog"}

    candidates = ned_query_names(name, arp_number)

    for query_name in candidates:
        try:
            result = Ned.query_object(query_name)
            if result is None or len(result) == 0:
                continue
            row = result[0]
            ra_deg = float(row["RA"])
            dec_deg = float(row["DEC"])
            ned_name = str(row["Object Name"]).strip()
            return {
                "ra_hours": ra_deg / 15.0,
                "dec_degrees": dec_deg,
                "ned_name": ned_name,
                "source": "NED",
            }
        except Exception:
            continue

    return {"ra_hours": fallback_ra_deg / 15.0, "dec_degrees": fallback_dec,
            "ned_name": "", "source": "catalog"}


def fetch_all_ned_coords(targets, delay=0.5):
    """
    Fetch NED coordinates for all targets with rate limiting.
    Args:
        targets: list of dicts with keys: arp_number, name
        delay: seconds between NED queries (default 0.5)
    Returns list of dicts: [{arp_number, ra_hours, dec_degrees, ned_name, source}]
    """
    results = []
    for t in targets:
        result = fetch_ned_coords(t["arp_number"], t["name"])
        result["arp_number"] = t["arp_number"]
        results.append(result)
        if result["source"] == "NED":
            time.sleep(delay)
    return results
