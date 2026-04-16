#!/usr/bin/env python3
"""
Arp Catalog NED Coordinate Fetcher
====================================
Fetches precise J2000 RA/Dec coordinates for all 338 Arp catalog objects
from the NASA/IPAC Extragalactic Database (NED), and saves them to a CSV
file that the other Arp project scripts will automatically use.

Run this script ONCE from your local machine. It makes one HTTP request per
target (338 total) with polite rate limiting. Typical runtime: 3–5 minutes.

Usage:
    python arp_ned_coords.py [--output arp_ned_coords.csv] [--delay 0.5]

Output CSV columns:
    arp, name, ned_name, ra_ned, dec_ned, source

Requirements:
    pip install astroquery pandas openpyxl

Once the output CSV is in the same folder as the other scripts, the plan
generators (arp_acp_generator.py, arp_session_planner.py) will automatically
use the NED coordinates in preference to the catalog coordinates.
"""

import argparse
import re
import time
from pathlib import Path

import pandas as pd

# Try importing astroquery; give a clear error if missing
try:
    from astroquery.ipac.ned import Ned
    from astroquery.exceptions import RemoteServiceError
    import astropy.units as u
    from astropy.coordinates import SkyCoord
except ImportError:
    print("ERROR: astroquery not installed. Run: pip install astroquery")
    raise SystemExit(1)

from arp_common import SEASONAL_PLAN_FILE, load_targets, parse_catalog_coords


# ---------------------------------------------------------------------------
# Name normalisation for NED queries
# ---------------------------------------------------------------------------

def ned_query_names(raw_name, arp_num):
    """
    Return a list of names to try querying NED with, in order of preference.
    NED is generally good with standard catalog designations.
    """
    name = raw_name.strip()

    # For compound names like "NGC 2535 + 36" or "NGC 2798 + 99",
    # query on the primary galaxy only
    primary = re.split(r'\s*\+\s*', name)[0].strip()
    primary = re.sub(r'\s+\+\s*$', '', primary).strip()
    primary = re.sub(r'\s+(comp|A|B|C)$', '', primary, flags=re.IGNORECASE).strip()

    candidates = []

    # MESSIER objects: NED prefers "M 51" format
    if primary.startswith("MESSIER "):
        num = primary.replace("MESSIER ", "").strip()
        candidates.append(f"M  {num}")
        candidates.append(f"M {num}")
        candidates.append(primary)

    # Standard catalog prefixes NED handles natively
    elif any(primary.startswith(p) for p in
             ["NGC", "UGC", "IC ", "IC0", "CGCG", "ESO", "VV ",
              "MCG", "MRK", "ARP", "Arp ", "UGCA", "NPM1G", "IRAS"]):
        candidates.append(primary)
        if name != primary:
            candidates.append(name)

    # Named objects
    elif primary in ("Holmberg II", "Wild's Triplet", "Stephan's Quint",
                     "Pisces Cloud", "Herzog 21", "I Zw 167"):
        ned_aliases = {
            "Holmberg II":      "Holmberg II",
            "Wild's Triplet":   "Wild's Triplet",
            "Stephan's Quint":  "Stephan's Quintet",
            "Pisces Cloud":     "Pisces Dwarf",
            "Herzog 21":        "HOLM 758B",
            "I Zw 167":         "I Zw 167",
        }
        candidates.append(ned_aliases.get(primary, primary))
        candidates.append(primary)

    else:
        candidates.append(primary)
        candidates.append(name)

    # Always fall back to "Arp NNN"
    candidates.append(f"Arp {arp_num}")

    # Deduplicate while preserving order
    seen = set()
    result = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result


# ---------------------------------------------------------------------------
# Single NED lookup with fallback cascade
# ---------------------------------------------------------------------------

def query_ned(name_candidates, fallback_ra, fallback_dec):
    """
    Try each name in name_candidates against NED.
    Returns (ra_deg, dec_deg, ned_name, source) where source is
    'NED' or 'catalog'.
    """
    for name in name_candidates:
        try:
            result = Ned.query_object(name)
            if result is None or len(result) == 0:
                continue
            row    = result[0]
            ra     = float(row['RA'])
            dec    = float(row['DEC'])
            ned_name = str(row['Object Name']).strip()
            return ra, dec, ned_name, 'NED'
        except RemoteServiceError:
            # NED returned "No object found" — try next candidate
            continue
        except Exception:
            # Network error, parse error, etc. — try next candidate
            continue

    # All candidates failed — use catalog coords
    return fallback_ra, fallback_dec, '', 'catalog'


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(args):
    out_path = Path(args.output)

    print(f"\n{'='*60}")
    print(f"  Arp Catalog NED Coordinate Fetcher")
    print(f"  Output: {out_path}")
    print(f"  Delay between queries: {args.delay}s")
    print(f"{'='*60}\n")

    # Resume from existing output if present
    existing = {}
    if out_path.exists() and not args.restart:
        existing_df = pd.read_csv(out_path)
        existing = {int(r['arp']): r for _, r in existing_df.iterrows()}
        print(f"  Resuming: {len(existing)} targets already fetched\n")

    print("  Loading catalog targets...")
    targets_df = load_targets()
    print(f"  {len(targets_df)} targets loaded\n")

    results   = []
    ned_count = 0
    fail_count = 0

    for idx, (_, row) in enumerate(targets_df.iterrows()):
        arp  = int(float(str(row['Arp #']).strip()))
        name = str(row['Common Name']).strip()

        # Skip if already fetched
        if arp in existing:
            r = existing[arp]
            results.append(r.to_dict())
            if r['source'] == 'NED':
                ned_count += 1
            continue

        # Catalog fallback coords (RA in degrees for output consistency)
        try:
            fallback_ra_deg, fallback_dec = parse_catalog_coords(
                row['RA (J2000)'], row['Dec (J2000)'])
        except Exception:
            fallback_ra_deg, fallback_dec = 0.0, 0.0

        candidates = ned_query_names(name, arp)
        ra_deg, dec_deg, ned_name, source = query_ned(
            candidates, fallback_ra_deg, fallback_dec)

        if source == 'NED':
            ned_count += 1
        else:
            fail_count += 1

        # Convert RA from degrees to decimal hours for plan files
        ra_hours = ra_deg / 15.0

        result = {
            'arp':      arp,
            'name':     name,
            'ned_name': ned_name,
            'ra_deg':   round(ra_deg,   6),
            'dec_deg':  round(dec_deg,  6),
            'ra_hours': round(ra_hours, 6),
            'source':   source,
        }
        results.append(result)

        status = f"NED: {ned_name}" if source == 'NED' else "FALLBACK (catalog)"
        print(f"  [{idx+1:3d}/338] Arp {arp:3d}  {name:<28}  {ra_hours:.6f}  {dec_deg:+.6f}  {status}")

        # Write incrementally so progress is preserved on interruption
        pd.DataFrame(results).to_csv(out_path, index=False)

        if source == 'NED':
            time.sleep(args.delay)

    # Final summary
    print(f"\n{'='*60}")
    print(f"  Done!")
    print(f"  NED lookups:      {ned_count}/338")
    print(f"  Catalog fallback: {fail_count}/338")
    print(f"  Output written:   {out_path}")
    print(f"{'='*60}")
    print(f"\n  Place {out_path.name} alongside the other Arp scripts.")
    print(f"  The plan generators will automatically use NED coordinates.\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Fetch precise NED coordinates for all 338 Arp catalog objects.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        '--output', default='arp_ned_coords.csv',
        help='Output CSV filename (default: arp_ned_coords.csv)'
    )
    parser.add_argument(
        '--delay', type=float, default=0.5,
        help='Seconds to wait between NED queries (default: 0.5)'
    )
    parser.add_argument(
        '--restart', action='store_true',
        help='Ignore existing output and fetch everything fresh'
    )
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    run(args)
