#!/usr/bin/env python3
"""
Arp Catalog Nightly Session Planner
====================================
Given a date and observatory, computes which Arp targets are observable
that night, applies moon avoidance, sorts by optimal imaging order
(by transit time), and outputs a ranked target list + ready-to-use ACP plan.

Usage:
    python arp_session_planner.py [--date YYYY-MM-DD] [--site SITE]
                                  [--min-hours N] [--min-el DEG]
                                  [--plan-tier TIER] [--output-dir DIR]

Examples:
    # Tonight at New Mexico
    python arp_session_planner.py

    # Specific date at Spain
    python arp_session_planner.py --date 2026-05-10 --site Spain

    # Only targets with 3+ observable hours
    python arp_session_planner.py --site "New Mexico" --min-hours 3
"""

import argparse
import datetime
import json
import math
import sys
from pathlib import Path

import ephem
import pandas as pd

DATA_DIR           = Path(__file__).parent
SEASONAL_PLAN_FILE = DATA_DIR / "Arp_Seasonal_Plan.xlsx"
TELESCOPE_FILE     = DATA_DIR / "itelescopesystems.xlsx"

OBSERVATORIES = {
    "New Mexico": {"lat": "33.0",  "lon": "-107.0", "elev": 1400, "utc_offset": -7,  "min_el": 30},
    "Spain":      {"lat": "38.0",  "lon": "-3.5",   "elev": 1200, "utc_offset":  2,  "min_el": 30},
    "Australia":  {"lat": "-31.3", "lon": "149.1",  "elev": 1100, "utc_offset": 10,  "min_el": 30},
    "Chile":      {"lat": "-30.0", "lon": "-70.7",  "elev": 1500, "utc_offset": -4,  "min_el": 30},
}

SITE_MAP = {
    "New Mexico / Spain":     ["New Mexico", "Spain"],
    "New Mexico / Australia": ["New Mexico", "Australia"],
    "Any site":               ["New Mexico", "Spain", "Chile", "Australia"],
    "Australia":              ["Australia"],
    "New Mexico":             ["New Mexico"],
    "Spain":                  ["Spain"],
    "Chile":                  ["Chile"],
}

TELESCOPE_TIERS = [
    (0,    3.0,  ["T17", "T32", "T21", "T11", "T25"]),
    (3.0,  7.0,  ["T11", "T21", "T26", "T30", "T17"]),
    (7.0,  20.0, ["T5",  "T20", "T26", "T71", "T75"]),
    (20.0, 999,  ["T14", "T8",  "T70", "T80"]),
]

PHASE_THRESHOLDS = [(25, 20), (50, 40), (75, 60), (101, 90)]
GOOD_MARGIN = 20

PLAN_TIERS = ["Plan-40", "Plan-90", "Plan-160", "Plan-290", "Plan-490"]

LRGB_COUNTS = [2, 1, 1, 1]  # per-repeat counts; plan uses #repeat 3
LUM_COUNTS  = [2]
INTERVAL    = 300


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_targets():
    df = pd.read_excel(SEASONAL_PLAN_FILE, sheet_name="All Objects", header=None)
    for i, row in df.iterrows():
        if any(str(v) == "Arp #" for v in row.values):
            df.columns = df.iloc[i]
            df = df.iloc[i + 1:].reset_index(drop=True)
            break
    df = df.dropna(subset=["Arp #"])
    df.columns = [str(c).strip() for c in df.columns]
    return df


def load_rates():
    df = pd.read_excel(TELESCOPE_FILE, sheet_name="Imaging Rates", header=None)
    for i, row in df.iterrows():
        if any(str(v).strip() == "Telescope" for v in row.values):
            header_row = i
            break
    else:
        return {}
    rates = {}
    for i in range(header_row + 1, len(df)):
        row = df.iloc[i]
        tel_id = str(row.iloc[0]).strip()
        if not tel_id or tel_id == "nan" or not tel_id.startswith("T"):
            continue
        vals = list(row.values)
        sess_rates = {}
        for j, plan in enumerate(PLAN_TIERS):
            try:    sess_rates[plan] = float(vals[j + 1])
            except: sess_rates[plan] = None
        rates[tel_id] = sess_rates
    return rates


# ---------------------------------------------------------------------------
# NED coordinates
# ---------------------------------------------------------------------------

def load_ned_coords():
    """Load NED coordinates from arp_ned_coords.csv if present."""
    ned_path = DATA_DIR / "arp_ned_coords.csv"
    if not ned_path.exists():
        return {}
    try:
        df = pd.read_csv(ned_path)
        return {int(r["arp"]): (float(r["ra_hours"]), float(r["dec_deg"]))
                for _, r in df.iterrows() if r.get("source") == "NED"}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

def parse_ra(s):
    s = str(s).strip()
    return s.replace(" ", ":") if " " in s else s


def parse_dec(s):
    s = str(s).strip()
    sign = "-" if s.startswith("-") else "+"
    body = s.lstrip("+-")
    parts = body.split()
    if len(parts) == 2:
        deg = parts[0]
        md  = float(parts[1])
        m, sc = int(md), int((md - int(md)) * 60)
        return f"{sign}{deg}:{m:02d}:{sc:02d}"
    return s


def sanitize_name(name):
    import re
    name = re.sub(r"[^\w\-+]", "_", str(name).strip())
    return re.sub(r"_+", "_", name).strip("_")


# ---------------------------------------------------------------------------
# Moon avoidance
# ---------------------------------------------------------------------------

def moon_risk(phase, sep):
    min_sep = next(m for p, m in PHASE_THRESHOLDS if phase < p)
    margin  = sep - min_sep
    if margin >= GOOD_MARGIN: return "Good"
    if margin >= 0:           return "Marginal"
    return "Avoid"


def get_moon_info(ra_str, dec_str, observer):
    moon   = ephem.Moon()
    target = ephem.FixedBody()
    target._ra  = ra_str
    target._dec = dec_str
    moon.compute(observer)
    target.compute(observer)
    phase = moon.phase
    sep   = math.degrees(ephem.separation(moon, target))
    risk  = moon_risk(phase, sep)
    return {"phase": round(phase, 1), "sep": round(sep, 1), "risk": risk}


# ---------------------------------------------------------------------------
# Visibility calculation
# ---------------------------------------------------------------------------

def get_dark_window(obs_key, date):
    """Return (eve_twi, morn_twi) as ephem.Date floats, or (None, None)."""
    cfg = OBSERVATORIES[obs_key]
    observer = ephem.Observer()
    observer.lat       = cfg["lat"]
    observer.lon       = cfg["lon"]
    observer.elevation = cfg["elev"]
    observer.horizon   = "-18"

    utc_noon = (12 - cfg["utc_offset"]) % 24
    observer.date = date.strftime(f"%Y/%m/%d {utc_noon:02d}:00:00")

    sun = ephem.Sun()
    try:
        eve_twi  = observer.next_setting(sun, use_center=True)
        observer.date = eve_twi
        morn_twi = observer.next_rising(sun, use_center=True)
        return float(eve_twi), float(morn_twi)
    except Exception:
        return None, None


def get_target_visibility(ra_str, dec_str, obs_key, eve_twi, morn_twi):
    """
    Return dict with observable hours, start/end/transit times (UTC ephem floats),
    or None if not observable.
    """
    cfg      = OBSERVATORIES[obs_key]
    observer = ephem.Observer()
    observer.lat       = cfg["lat"]
    observer.lon       = cfg["lon"]
    observer.elevation = cfg["elev"]
    observer.horizon   = str(cfg["min_el"])

    target = ephem.FixedBody()
    target._ra  = ra_str
    target._dec = dec_str

    # Altitude at start/end of dark window
    observer.date = eve_twi
    target.compute(observer)
    alt_eve = math.degrees(target.alt)

    observer.date = morn_twi
    target.compute(observer)
    alt_morn = math.degrees(target.alt)

    # Determine observable start
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

    # Determine observable end
    if alt_morn >= cfg["min_el"]:
        obs_end = morn_twi
    else:
        observer.date = obs_start
        try:
            sett = float(observer.next_setting(target))
            obs_end = min(sett, morn_twi)
        except ephem.AlwaysUpError:
            obs_end = morn_twi
        except ephem.NeverUpError:
            obs_end = obs_start

    if obs_end <= obs_start:
        return None

    obs_hrs = (obs_end - obs_start) * 24

    # Transit time
    observer.date = obs_start
    try:
        trans = float(observer.next_transit(target))
        if trans > morn_twi:
            trans = (obs_start + obs_end) / 2  # fallback midpoint
    except Exception:
        trans = (obs_start + obs_end) / 2

    return {
        "obs_start":  obs_start,
        "obs_end":    obs_end,
        "transit":    trans,
        "hours":      round(obs_hrs, 1),
    }


def ephem_to_local(ephem_float, utc_offset):
    dt = ephem.Date(ephem_float).datetime() + datetime.timedelta(hours=utc_offset)
    return dt.strftime("%H:%M")


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------

def estimate_cost(strategy, rate_per_min):
    if rate_per_min is None:
        return None
    if strategy == "LRGB":
        total_exp = sum(LRGB_COUNTS) * INTERVAL
    else:
        total_exp = sum(LUM_COUNTS) * INTERVAL
    overhead = 180  # slew + platesolve
    session_min = (total_exp + overhead) / 60
    return round(session_min * rate_per_min)


# ---------------------------------------------------------------------------
# Telescope assignment (simplified — by size, matching site)
# ---------------------------------------------------------------------------

def assign_telescope(size, obs_key):
    site_prefix = obs_key.split()[0]  # "New" or "Spain" or "Australia" or "Chile"
    for min_s, max_s, tel_ids in TELESCOPE_TIERS:
        if min_s <= size < max_s:
            return tel_ids[0]
    return "T11"


# ---------------------------------------------------------------------------
# ACP plan builder
# ---------------------------------------------------------------------------

def build_session_plan(targets_tonight, obs_key, date, plan_tier, no_adaptive=False, dither=False, tiff=False):
    # Calculate imaging time and total duration
    imaging_secs = 0
    for t in targets_tonight:
        if t['strategy'] == 'LRGB':
            imaging_secs += sum(LRGB_COUNTS) * INTERVAL
        else:
            imaging_secs += sum(LUM_COUNTS) * INTERVAL
    overhead_secs = len(targets_tonight) * 180 + 300  # slew + startup
    total_secs = imaging_secs + overhead_secs

    def fmt(secs):
        h, m = int(secs // 3600), int((secs % 3600) // 60)
        return f'{h}h {m:02d}m' if h > 0 else f'{m}m'

    total_cost = sum(t.get('cost_pts') or 0 for t in targets_tonight)

    lines = []
    lines.append(f"; ============================================================")
    lines.append(f"; Arp Nightly Session Plan")
    lines.append(f"; Date        : {date}")
    lines.append(f"; Observatory : {obs_key}")
    lines.append(f"; Targets     : {len(targets_tonight)}")
    lines.append(f"; Imaging time : {fmt(imaging_secs)}  (shutter-open only)")
    lines.append(f"; Total duration: {fmt(total_secs)}  (imaging + slew/overhead)")
    lines.append(f"; Est. cost    : ~{total_cost:,} pts (session billing, {plan_tier})")
    lines.append(f"; Plan tier    : {plan_tier}")
    lines.append(f"; Generated    : Arp Session Planner")
    lines.append(f"; ============================================================")
    lines.append("")
    lines.append("#BillingMethod Session")
    lines.append("#RESUME")  # allow plan restart after weather interruption
    lines.append("#FIRSTLAST")  # only create previews for first and last images
    if no_adaptive:
        lines.append("#FORCESTARTUP")
        lines.append("#NOADAPTIVE")
    if dither:
        lines.append("#DITHER")
    if tiff:
        lines.append("#TIFF")
    lines.append("")
    lines.append("#repeat 3")
    lines.append("")

    for t in targets_tonight:
        strategy = t["strategy"]
        name     = sanitize_name(f"Arp{int(t['arp']):03d}_{t['name']}")
        moon_str = f"moon {t['moon']['phase']:.0f}% sep {t['moon']['sep']:.0f}deg"
        ra_dec   = round(t["ra_dec"], 6)
        dec_dec  = round(t["dec_dec"], 6)

        if strategy == "LRGB":
            filters   = "Luminance,Red,Green,Blue"
            counts    = ",".join(str(c) for c in LRGB_COUNTS)
            intervals = ",".join(str(INTERVAL) for _ in LRGB_COUNTS)
            binnings  = "1,2,2,2"  # Luminance bin 1, RGB bin 2
        else:
            filters   = "Luminance"
            counts    = str(LUM_COUNTS[0])
            intervals = str(INTERVAL)
            binnings  = "1"

        lines.append(f"; --- Arp {t['arp']}: {t['name']}  [{t['hours']}h window, transit {t['transit_local']}, {moon_str}] ---")
        lines.append(f"#count {counts}")
        lines.append(f"#interval {intervals}")
        lines.append(f"#binning {binnings}")
        lines.append(f"#filter {filters}")
        lines.append(f"{name}\t{ra_dec}\t{dec_dec}")
        lines.append("")

    lines.append("#shutdown")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(args):
    date    = datetime.date.fromisoformat(args.date) if args.date else datetime.date.today()
    obs_key = args.site
    plan_tier = args.plan_tier

    print(f"\n{'='*60}")
    print(f"  Arp Nightly Session Planner")
    print(f"  Date: {date}  |  Site: {obs_key}  |  Tier: {plan_tier}")
    print(f"{'='*60}\n")

    ned_coords = load_ned_coords()
    if ned_coords:
        print(f"  NED coordinates loaded for {len(ned_coords)} targets.")
    else:
        print(f"  No arp_ned_coords.csv found — using catalog coordinates.")

    targets_df = load_targets()
    rates      = load_rates()

    # Dark window
    eve_twi, morn_twi = get_dark_window(obs_key, date)
    if eve_twi is None:
        print("  Could not compute dark window for this date/site.")
        sys.exit(1)

    cfg = OBSERVATORIES[obs_key]
    dark_hrs = (morn_twi - eve_twi) * 24
    print(f"  Dark window: {ephem_to_local(eve_twi, cfg['utc_offset'])} – "
          f"{ephem_to_local(morn_twi, cfg['utc_offset'])} local  ({dark_hrs:.1f}h)\n")

    # Moon at midnight local
    observer = ephem.Observer()
    observer.lat       = cfg["lat"]
    observer.lon       = cfg["lon"]
    observer.elevation = cfg["elev"]
    observer.date      = (eve_twi + morn_twi) / 2
    moon = ephem.Moon()
    moon.compute(observer)
    print(f"  Moon phase: {moon.phase:.1f}%\n")

    # Process targets
    results = []
    for _, row in targets_df.iterrows():
        arp      = int(float(str(row["Arp #"]).strip()))
        name     = str(row["Common Name"]).strip()
        # Use NED coordinates if available, else parse from catalog
        if arp in ned_coords:
            ra_decimal, dec_decimal = ned_coords[arp]
            # Convert NED decimal hours → ephem RA string
            _h = int(ra_decimal); _m = int((ra_decimal-_h)*60)
            _s = ((ra_decimal-_h)*60-_m)*60
            ra_str = f"{_h:02d}:{_m:02d}:{_s:05.2f}"
            # Convert NED decimal degrees → ephem Dec string
            _sg = "-" if dec_decimal < 0 else "+"
            _ad = abs(dec_decimal); _dd = int(_ad)
            _dm = int((_ad-_dd)*60); _ds = ((_ad-_dd)*60-_dm)*60
            dec_str = f"{_sg}{_dd:02d}:{_dm:02d}:{_ds:04.1f}"
        else:
            ra_str  = parse_ra(row["RA (J2000)"])
            dec_str = parse_dec(row["Dec (J2000)"])
            ra_parts_d = ra_str.split(":")
            ra_decimal = float(ra_parts_d[0]) + float(ra_parts_d[1])/60 + float(ra_parts_d[2])/3600
            dec_sign = -1 if dec_str.startswith("-") else 1
            dec_parts_d = dec_str.lstrip("+-").split(":")
            dec_decimal = dec_sign * (float(dec_parts_d[0]) + float(dec_parts_d[1])/60 + float(dec_parts_d[2])/3600)

        site_str = str(row.get("Best Site", "Any site")).strip()
        strategy = str(row.get("Filter Strategy", "Luminance")).strip()
        size     = float(row["Size (arcmin)"]) if row["Size (arcmin)"] else 3.0

        # Check site compatibility
        compatible_sites = SITE_MAP.get(site_str, ["New Mexico"])
        if obs_key not in compatible_sites:
            continue

        # Visibility
        vis = get_target_visibility(ra_str, dec_str, obs_key, eve_twi, morn_twi)
        if not vis or vis["hours"] < args.min_hours:
            continue

        # Moon
        observer.date = vis["transit"]
        moon_info = get_moon_info(ra_str, dec_str, observer)
        if args.moon_ok_only and moon_info["risk"] == "Avoid":
            continue

        # Telescope & cost
        tel  = assign_telescope(size, obs_key)
        rate = rates.get(tel, {}).get(plan_tier)
        cost = estimate_cost(strategy, rate)

        # RA/Dec formatted for ACP
        ra_acp  = ra_str
        dec_acp = dec_str

        results.append({
            "arp":           arp,
            "name":          name,
            "ra_acp":        ra_acp,
            "dec_acp":       dec_acp,
            "ra_dec":        ra_decimal,
            "dec_dec":       dec_decimal,
            "strategy":      strategy,
            "size":          size,
            "telescope":     tel,
            "hours":         vis["hours"],
            "start_local":   ephem_to_local(vis["obs_start"], cfg["utc_offset"]),
            "end_local":     ephem_to_local(vis["obs_end"],   cfg["utc_offset"]),
            "transit_local": ephem_to_local(vis["transit"],   cfg["utc_offset"]),
            "transit_ephem": vis["transit"],
            "moon":          moon_info,
            "cost_pts":      cost,
        })

    # Sort by transit time
    results.sort(key=lambda t: t["transit_ephem"])

    # Report
    print(f"  {'Arp':>4}  {'Name':<22} {'Window':>13}  {'Transit':>7}  "
          f"{'Moon%':>5}  {'Sep':>6}  {'Risk':<8}  {'Tel':>4}  {'Pts':>6}  {'Filters'}")
    print(f"  {'-'*4}  {'-'*22} {'-'*13}  {'-'*7}  {'-'*5}  {'-'*6}  {'-'*8}  {'-'*4}  {'-'*6}  {'-'*8}")

    good = [t for t in results if t["moon"]["risk"] != "Avoid"]
    marg = [t for t in results if t["moon"]["risk"] == "Marginal"]
    avoid = [t for t in results if t["moon"]["risk"] == "Avoid"]

    for t in results:
        risk_flag = "  " if t["moon"]["risk"] == "Good" else ("~ " if t["moon"]["risk"] == "Marginal" else "! ")
        cost_str  = str(t["cost_pts"]) if t["cost_pts"] else "n/a"
        print(f"  {risk_flag}{t['arp']:>4}  {t['name']:<22} "
              f"{t['start_local']}-{t['end_local']}  "
              f"{t['transit_local']:>7}  "
              f"{t['moon']['phase']:>5.1f}  {t['moon']['sep']:>5.1f}°  "
              f"{t['moon']['risk']:<8}  {t['telescope']:>4}  {cost_str:>6}  {t['strategy']}")

    print(f"\n  {len(results)} observable targets  "
          f"({len(good)} good, {len(marg)} marginal, {len(avoid)} avoid moon)")

    total_cost = sum(t["cost_pts"] for t in results if t["cost_pts"])
    print(f"  Total session cost (session billing): ~{total_cost:,} pts")

    # Write ACP plan
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_name = f"Arp_Session_{obs_key.replace(' ','_')}_{date}.txt"
    plan_path = out_dir / plan_name
    plan_text = build_session_plan(results, obs_key, date, plan_tier, args.no_adaptive, args.dither, args.tiff)
    with open(plan_path, "w") as f:
        f.write(plan_text)
    print(f"\n  ACP plan: {plan_path}")

    # Write JSON summary for dashboard
    summary_path = out_dir / f"session_{obs_key.replace(' ','_')}_{date}.json"
    with open(summary_path, "w") as f:
        json.dump({
            "date": str(date),
            "site": obs_key,
            "dark_start": ephem_to_local(eve_twi, cfg["utc_offset"]),
            "dark_end":   ephem_to_local(morn_twi, cfg["utc_offset"]),
            "dark_hours": round(dark_hrs, 1),
            "moon_phase": round(moon.phase, 1),
            "targets": results,
        }, f, indent=2)
    print(f"  JSON summary: {summary_path}\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate nightly Arp session plan with visibility and moon avoidance.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--date", default=None,
        help="Observing date YYYY-MM-DD (default: today)")
    parser.add_argument("--site", default="New Mexico",
        choices=list(OBSERVATORIES.keys()),
        help="Observatory site (default: New Mexico)")
    parser.add_argument("--min-hours", type=float, default=1.5,
        help="Minimum observable hours to include a target (default: 1.5)")
    parser.add_argument("--min-el", type=int, default=None,
        help="Override minimum elevation in degrees (site default: 30°; iTelescope enforces 15°, suggests 45°)")
    parser.add_argument("--plan-tier", default="Plan-40",
        choices=PLAN_TIERS,
        help="Membership plan tier for cost estimates (default: Plan-40)")
    parser.add_argument("--output-dir", default="session_plans",
        help="Directory for output files (default: session_plans/)")
    parser.add_argument("--moon-ok-only", action="store_true",
        help="Exclude targets with Avoid moon rating")
    parser.add_argument(
        "--no-adaptive", action="store_true",
        help="Add #FORCESTARTUP + #NOADAPTIVE directives to disable adaptive focusing"
    )
    parser.add_argument(
        "--dither", action="store_true",
        help="Add #DITHER directive to initiate small positional changes between exposures"
    )
    parser.add_argument(
        "--tiff", action="store_true",
        help="Add #TIFF directive to also save images in 16-bit TIFF format"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(args)
