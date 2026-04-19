#!/usr/bin/env python3
"""
Arp Catalog Moon Avoidance Calendar Generator
==============================================
Calculates moon phase, separation, and imaging risk for every Arp target
over a configurable window, and outputs a JSON file for use in the dashboard.

Usage:
    python arp_moon_calendar.py [--days N] [--output FILE]

Examples:
    python arp_moon_calendar.py --days 90
    python arp_moon_calendar.py --days 60 --output moon_data.json
"""

import argparse
import datetime
import json
import math
from pathlib import Path

import ephem

from arp_common import (
    OBSERVATORIES, SITE_MAP, SITE_UTAH,
    load_targets, moon_risk, parse_ra, parse_dec,
)


def build_observer(obs_key):
    cfg = OBSERVATORIES[obs_key]
    obs = ephem.Observer()
    obs.lat       = cfg["lat"]
    obs.lon       = cfg["lon"]
    obs.elevation = cfg["elev"]
    return obs, cfg["utc_offset"]


def calc_windows(ra_str, dec_str, obs_key, start_date, days):
    """
    Return list of daily dicts: {d, p, s, r}
      d = ISO date string
      p = moon phase %
      s = moon-target separation degrees
      r = risk code G/M/A
    """
    observer, utc_offset = build_observer(obs_key)
    utc_hour = (24 - utc_offset) % 24

    moon   = ephem.Moon()
    target = ephem.FixedBody()
    target._ra  = ra_str
    target._dec = dec_str

    windows = []
    for d in range(days):
        date = start_date + datetime.timedelta(days=d)
        observer.date = date.strftime(f"%Y/%m/%d {utc_hour:02d}:00:00")
        moon.compute(observer)
        target.compute(observer)
        phase = moon.phase
        sep   = math.degrees(ephem.separation(moon, target))
        windows.append({
            "d": date.isoformat(),
            "p": round(phase, 1),
            "s": round(sep, 1),
            "r": moon_risk(phase, sep),
        })
    return windows


def run(args):
    today = datetime.date.today()
    days  = args.days

    print(f"\n{'='*55}")
    print(f"  Arp Moon Avoidance Calendar")
    print(f"  Start: {today}  |  Window: {days} days")
    print(f"{'='*55}\n")

    print("Loading targets...")
    targets_df = load_targets()
    n = len(targets_df)
    print(f"  {n} targets loaded.\n")

    # Moon phase calendar — one entry per day for header info
    moon_obj  = ephem.Moon()
    phase_cal = []
    obs, utc_offset = build_observer(SITE_UTAH)
    utc_hour = (24 - utc_offset) % 24
    for d in range(days):
        date = today + datetime.timedelta(days=d)
        obs.date = date.strftime(f"%Y/%m/%d {utc_hour:02d}:00:00")
        moon_obj.compute(obs)
        phase_cal.append({"d": date.isoformat(), "p": round(moon_obj.phase, 1)})

    # Next new/full moon
    next_new  = ephem.Date(ephem.next_new_moon(today.strftime("%Y/%m/%d"))).datetime().date().isoformat()
    next_full = ephem.Date(ephem.next_full_moon(today.strftime("%Y/%m/%d"))).datetime().date().isoformat()

    results = []
    for idx, (_, row) in enumerate(targets_df.iterrows()):
        arp      = int(float(str(row["Arp #"]).strip()))
        name     = str(row["Common Name"]).strip()
        ra_str   = parse_ra(row["RA (J2000)"])
        dec_str  = parse_dec(row["Dec (J2000)"])
        site_str = str(row.get("Best Site", "Any site")).strip()
        obs_key  = SITE_MAP.get(site_str, [SITE_UTAH])[0]
        season   = str(row.get("season", "")).strip() if "season" in row else ""

        windows   = calc_windows(ra_str, dec_str, obs_key, today, days)
        good_days = sum(1 for w in windows if w["r"] == "G")
        next_good = next((w["d"] for w in windows if w["r"] == "G"), None)
        next_avoid= next((w["d"] for w in windows if w["r"] == "A"), None)

        results.append({
            "arp":        arp,
            "name":       name,
            "obs":        obs_key,
            "good_days":  good_days,
            "next_good":  next_good,
            "next_avoid": next_avoid,
            "windows":    windows,
        })

        if (idx + 1) % 50 == 0 or (idx + 1) == n:
            pct = round((idx + 1) / n * 100)
            print(f"  Processed {idx+1}/{n} targets ({pct}%)")

    output = {
        "generated":  today.isoformat(),
        "days":       days,
        "next_new":   next_new,
        "next_full":  next_full,
        "phase_cal":  phase_cal,
        "targets":    results,
    }

    out_path = Path(args.output)
    with open(out_path, "w") as f:
        json.dump(output, f, separators=(",", ":"))

    size_kb = round(out_path.stat().st_size / 1024)
    print(f"\n{'='*55}")
    print(f"  Done! Written to: {out_path}  ({size_kb} KB)")
    print(f"  Next new moon:  {next_new}")
    print(f"  Next full moon: {next_full}")
    print(f"{'='*55}\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate moon avoidance calendar JSON for Arp catalog targets.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--days", type=int, default=90,
        help="Number of days to calculate from today (default: 90)"
    )
    parser.add_argument(
        "--output", default="arp_moon_data.json",
        help="Output JSON filename (default: arp_moon_data.json)"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(args)
