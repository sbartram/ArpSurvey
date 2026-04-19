#!/usr/bin/env python3
"""
Arp Catalog ACP Plan Generator for iTelescope
=============================================
Reads the Arp seasonal plan and iTelescope telescope specs,
matches each target to the best telescope, and generates
ACP-format observing plan .txt files ready to upload to iTelescope.

Also calculates per-plan imaging duration and iTelescope point cost
for every plan, and writes a full cost/duration summary CSV.

Usage:
    python arp_acp_generator.py [--season SEASON] [--telescope TELESCOPE]
                                [--output-dir OUTPUT_DIR] [--targets-per-plan N]
                                [--exposure SECONDS] [--count N] [--repeat N]
                                [--plan-tier PLAN]

Examples:
    # Generate all Spring plans, auto-assign telescopes
    python arp_acp_generator.py --season Spring

    # Generate Summer plans for T20 only, 4 targets per plan file
    python arp_acp_generator.py --season Summer --telescope T20 --targets-per-plan 4

    # Generate plans for all seasons
    python arp_acp_generator.py --season All

    # Custom exposure settings with Plan-40 pricing
    python arp_acp_generator.py --season Spring --exposure 300 --count 2 --repeat 3 --plan-tier Plan-40
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from arp_common import (
    TELESCOPE_FILE,
    TELESCOPE_TIERS, SITE_TELESCOPES, PLAN_TIERS, SEASON_SHEETS,
    LRGB_FILTERS, LUM_FILTERS,
    OVERHEAD_PER_TARGET_SECS, OVERHEAD_SESSION_SECS,
    load_telescopes, load_rates, load_targets, load_ned_coords, sanitize_name,
)


# ---------------------------------------------------------------------------
# Telescope matching
# ---------------------------------------------------------------------------

def parse_fov(telescope_row):
    """Return (fov_x, fov_y) in arcminutes as floats, or (None, None)."""
    try:
        x = float(telescope_row["FOV X (arcmins)"])
        y = float(telescope_row["FOV Y (arcmins)"])
        return x, y
    except (ValueError, TypeError):
        return None, None


def target_fits_telescope(size_arcmin, fov_x, fov_y, margin=1.5):
    """Return True if the target fits in the FOV with a margin factor."""
    if fov_x is None or fov_y is None:
        return False
    min_fov = min(fov_x, fov_y)
    return size_arcmin * margin <= min_fov


def assign_telescope(row, telescopes, preferred_telescope=None):
    """
    Determine the best telescope for a target.
    If preferred_telescope is set and valid, use it.
    Otherwise auto-assign from TELESCOPE_TIERS filtered by Best Site.
    """
    if preferred_telescope and preferred_telescope in telescopes.index:
        return preferred_telescope

    try:
        size = float(row["Size (arcmin)"])
    except (ValueError, TypeError):
        size = 3.0  # default if unknown

    best_site = str(row.get("Best Site", ""))

    # Build candidate list from tiers
    candidates = []
    for min_s, max_s, tel_ids in TELESCOPE_TIERS:
        if min_s <= size < max_s:
            candidates = tel_ids
            break

    # Filter by site preference if specified
    site_preferred = []
    for site_key, site_tels in SITE_TELESCOPES.items():
        if site_key.lower() in best_site.lower():
            site_preferred.extend(site_tels)

    # Try site-preferred candidates first, then all candidates
    ordered = [t for t in candidates if t in site_preferred] + \
              [t for t in candidates if t not in site_preferred]

    for tel_id in ordered:
        if tel_id not in telescopes.index:
            continue
        fov_x, fov_y = parse_fov(telescopes.loc[tel_id])
        if target_fits_telescope(size, fov_x, fov_y):
            return tel_id

    # Fallback: return first available candidate
    for tel_id in candidates:
        if tel_id in telescopes.index:
            return tel_id

    return "T11"  # final fallback


# ---------------------------------------------------------------------------
# Duration and cost estimation
# ---------------------------------------------------------------------------

def calc_plan_duration(batch_df, interval, repeat, lrgb_counts, lum_counts):
    """
    Estimate total wall-clock duration of a plan in seconds.
    Accounts for: exposures per filter per target, per-target overhead,
    session startup overhead, and #REPEAT loops.
    """
    exposure_secs = 0
    for _, row in batch_df.iterrows():
        strategy = str(row.get("Filter Strategy", "Luminance")).strip()
        if strategy == "LRGB":
            total_exposures = sum(lrgb_counts)
        else:
            total_exposures = sum(lum_counts)
        exposure_secs += total_exposures * interval

    exposure_secs_total = exposure_secs * repeat
    target_overhead = len(batch_df) * OVERHEAD_PER_TARGET_SECS
    total_secs = (exposure_secs + target_overhead) * repeat + OVERHEAD_SESSION_SECS
    return total_secs, exposure_secs_total


def format_duration(total_secs):
    """Return a human-readable duration string: e.g. '1h 23m'."""
    h = int(total_secs // 3600)
    m = int((total_secs % 3600) // 60)
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def calc_plan_cost(batch_df, tel_id, interval, repeat,
                   lrgb_counts, lum_counts, rates, plan_tier, billing_mode):
    """
    Estimate iTelescope point cost for a plan.

    billing_mode: 'session' — charged per minute of session time
                  'exposure' — charged per minute of actual exposure time
    plan_tier:    one of PLAN_TIERS, e.g. 'Plan-160'

    Returns (points_float, rate_used) or (None, None) if rate unavailable.
    """
    tel_rates = rates.get(tel_id)
    if not tel_rates:
        return None, None

    rate = tel_rates[billing_mode].get(plan_tier)
    if rate is None or rate == 0:
        return 0.0, 0.0  # free telescope (T33, T68)

    if billing_mode == "session":
        total_secs, _ = calc_plan_duration(batch_df, interval, repeat, lrgb_counts, lum_counts)
        minutes = total_secs / 60
    else:
        # Exposure billing: only count actual shutter-open time
        exposure_secs = 0
        for _, row in batch_df.iterrows():
            strategy = str(row.get("Filter Strategy", "Luminance")).strip()
            if strategy == "LRGB":
                total_exposures = sum(lrgb_counts)
            else:
                total_exposures = sum(lum_counts)
            exposure_secs += total_exposures * interval
        exposure_secs *= repeat
        minutes = exposure_secs / 60

    hours = minutes / 60
    points = rate * hours
    return round(points, 1), rate


# ---------------------------------------------------------------------------
# ACP plan generation
# ---------------------------------------------------------------------------

def build_acp_header(plan_name, telescope_id, season, target_count,
                     duration_str=None, imaging_time_str=None,
                     session_cost=None, exposure_cost=None, plan_tier=None):
    """Return the comment header block for an ACP plan."""
    cost_lines = ""
    if imaging_time_str:
        cost_lines += f"; Imaging time    : {imaging_time_str}  (shutter-open only)\n"
    if duration_str:
        cost_lines += f"; Total duration  : {duration_str}  (imaging + slew/overhead)\n"
    if plan_tier and session_cost is not None:
        cost_lines += f"; Est. Cost ({plan_tier})\n"
        if session_cost == 0.0:
            cost_lines += ";   Session billing : FREE\n"
            cost_lines += ";   Exposure billing: FREE\n"
        else:
            cost_lines += f";   Session billing : ~{session_cost:.0f} pts\n"
            cost_lines += f";   Exposure billing: ~{exposure_cost:.0f} pts\n"
        cost_lines += ";\n"

    return f"""; ============================================================
; Arp Catalog Observing Plan
; Plan Name    : {plan_name}
; Telescope    : {telescope_id}
; Season       : {season}
; Targets      : {target_count}
; Generated    : Arp ACP Generator
;
{cost_lines}; Upload to iTelescope via: My Observing Plans > Upload File
; Note: Plans are telescope-specific — upload to {telescope_id} only
; ============================================================

"""


def build_target_block(row, filter_strategy, interval, lrgb_counts, lum_counts,
                        ned_coords=None):
    """Return ACP target block for a single Arp object in iTelescope format."""
    arp_num  = str(row["Arp #"]).strip()
    name     = str(row["Common Name"]).strip()
    size     = row.get("Size (arcmin)", "?")
    arp_int  = int(float(arp_num))
    acp_name = sanitize_name(f"Arp{arp_int:03d}_{name}")

    # Use NED coordinates if available, otherwise parse from catalog
    if ned_coords and arp_int in ned_coords:
        ra_dec, dec_dec = ned_coords[arp_int]
    else:
        ra_str = str(row["RA (J2000)"]).strip().split()
        ra_dec = float(ra_str[0]) + float(ra_str[1])/60 + (float(ra_str[2]) if len(ra_str)>2 else 0)/3600
        dec_str = str(row["Dec (J2000)"]).strip()
        sign = -1 if dec_str.startswith("-") else 1
        dec_parts = dec_str.lstrip("+-").split()
        dec_dec = sign * (float(dec_parts[0]) + float(dec_parts[1])/60)

    if filter_strategy == "LRGB":
        filters   = ",".join(LRGB_FILTERS)
        counts    = ",".join(str(c) for c in lrgb_counts)
        intervals = ",".join(str(interval) for _ in lrgb_counts)
        binnings  = "1,2,2,2"  # Luminance bin 1, RGB bin 2
    else:
        filters   = LUM_FILTERS[0]
        counts    = str(lum_counts[0])
        intervals = str(interval)
        binnings  = "1"

    lines = []
    lines.append(f"; --- Arp {arp_num}: {name}  (size: {size}') ---")
    lines.append(f"#count {counts}")
    lines.append(f"#interval {intervals}")
    lines.append(f"#binning {binnings}")
    lines.append(f"#filter {filters}")
    lines.append(f"{acp_name}\t{ra_dec:.6f}\t{dec_dec:.6f}")
    lines.append("")
    return "\n".join(lines)


def generate_plan_text(plan_name, telescope_id, season, targets_df,
                       interval, binning, repeat,
                       lrgb_counts, lum_counts,
                       duration_str=None, imaging_time_str=None,
                       session_cost=None, exposure_cost=None,
                       plan_tier=None, no_adaptive=False,
                       dither=False, tiff=False, ned_coords=None):
    """Assemble a complete ACP plan in iTelescope format."""
    parts = []
    parts.append(build_acp_header(
        plan_name, telescope_id, season, len(targets_df),
        duration_str=duration_str, imaging_time_str=imaging_time_str,
        session_cost=session_cost,
        exposure_cost=exposure_cost, plan_tier=plan_tier
    ))

    # Global directives
    parts.append(f"#BillingMethod Session\n")
    parts.append("#RESUME\n")  # allow plan restart after weather interruption
    parts.append("#FIRSTLAST\n")  # only create previews for first and last images
    if no_adaptive:
        parts.append("#FORCESTARTUP\n#NOADAPTIVE\n")
    if dither:
        parts.append("#DITHER\n")
    if tiff:
        parts.append("#TIFF\n")
    parts.append(f"#repeat {repeat}\n")

    for _, row in targets_df.iterrows():
        strategy = str(row.get("Filter Strategy", "Luminance")).strip()
        block = build_target_block(row, strategy, interval, lrgb_counts, lum_counts,
                                   ned_coords=ned_coords or {})
        parts.append(block)

    parts.append("#shutdown\n")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run(args):
    print(f"\n{'='*60}")
    print(f"  Arp ACP Plan Generator")
    print(f"  Season: {args.season} | Telescope: {args.telescope or 'auto'}")
    print(f"  Plan tier: {args.plan_tier} | Billing: session + exposure shown")
    print(f"{'='*60}\n")

    # Load data
    print("Loading telescope data...")
    telescopes = load_telescopes(TELESCOPE_FILE)
    print(f"  {len(telescopes)} telescopes loaded.")

    ned_coords = load_ned_coords()
    if ned_coords:
        print(f"  NED coordinates loaded for {len(ned_coords)} targets.")
    else:
        print(f"  No arp_ned_coords.csv found — using catalog coordinates.")
        print(f"  Run arp_ned_coords.py to fetch precise NED coordinates.")

    print("Loading imaging rates...")
    rates = load_rates(TELESCOPE_FILE)
    print(f"  {len(rates)} telescopes with rate data.")

    print(f"Loading targets for season: {args.season}...")
    sheet_name = SEASON_SHEETS.get(args.season)
    if not sheet_name:
        print(f"Unknown season '{args.season}'. Choose from: {list(SEASON_SHEETS)}")
        sys.exit(1)
    targets = load_targets(sheet_name=sheet_name)
    print(f"  {len(targets)} targets loaded.\n")

    # Assign telescopes
    targets = targets.copy()
    targets["Assigned_Telescope"] = targets.apply(
        lambda row: assign_telescope(row, telescopes, args.telescope),
        axis=1
    )

    # Exposure settings
    interval    = args.exposure
    binning     = args.binning
    repeat      = args.repeat
    plan_tier   = args.plan_tier
    lrgb_counts = [args.count, max(1, args.count // 2),
                   max(1, args.count // 2), max(1, args.count // 2)]
    lum_counts  = [args.count * args.repeat // args.repeat]  # lum count per repeat

    # Output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Group targets by assigned telescope
    groups = targets.groupby("Assigned_Telescope")
    total_plans       = 0
    total_session_pts = 0.0
    total_exposure_pts= 0.0
    total_duration_s  = 0
    plan_log          = []

    print(f"  {'Plan':<40} {'Targets':>7} {'Duration':>10} {'Session pts':>12} {'Exposure pts':>13}")
    print(f"  {'-'*40} {'-'*7} {'-'*10} {'-'*12} {'-'*13}")

    for tel_id, group in groups:
        group      = group.reset_index(drop=True)
        batch_size = args.targets_per_plan
        batches    = [group.iloc[i:i+batch_size] for i in range(0, len(group), batch_size)]

        for b_idx, batch in enumerate(batches):
            batch_num  = b_idx + 1
            season_tag = args.season.replace(" ", "_").replace("(", "").replace(")", "")
            plan_name  = f"Arp_{season_tag}_{tel_id}_batch{batch_num:02d}"
            filename   = output_dir / f"{plan_name}.txt"

            # Duration
            duration_secs, imaging_secs = calc_plan_duration(batch, interval, repeat, lrgb_counts, lum_counts)
            duration_str      = format_duration(duration_secs)
            imaging_time_str  = format_duration(imaging_secs)

            # Cost — both billing modes
            session_pts,  session_rate  = calc_plan_cost(
                batch, tel_id, interval, repeat, lrgb_counts, lum_counts,
                rates, plan_tier, "session"
            )
            exposure_pts, exposure_rate = calc_plan_cost(
                batch, tel_id, interval, repeat, lrgb_counts, lum_counts,
                rates, plan_tier, "exposure"
            )

            plan_text = generate_plan_text(
                plan_name, tel_id, args.season, batch,
                interval, binning, repeat, lrgb_counts, lum_counts,
                duration_str=duration_str,
                imaging_time_str=imaging_time_str,
                session_cost=session_pts,
                exposure_cost=exposure_pts,
                plan_tier=plan_tier,
                no_adaptive=args.no_adaptive,
                dither=args.dither,
                tiff=args.tiff,
                ned_coords=ned_coords,
            )

            with open(filename, "w") as f:
                f.write(plan_text)

            arp_nums = [str(r["Arp #"]).strip() for _, r in batch.iterrows()]

            s_pts_str = f"{session_pts:.0f}"  if session_pts  is not None else "n/a"
            e_pts_str = f"{exposure_pts:.0f}" if exposure_pts is not None else "n/a"
            print(f"  {plan_name:<40} {len(batch):>7} {duration_str:>10} {s_pts_str:>12} {e_pts_str:>13}")

            if session_pts:
                total_session_pts  += session_pts
            if exposure_pts:
                total_exposure_pts += exposure_pts
            total_duration_s += duration_secs

            log_entry = {
                "Plan":               plan_name,
                "Telescope":          tel_id,
                "Targets":            len(batch),
                "Arp Numbers":        ", ".join(arp_nums),
                "Duration":           duration_str,
                "Duration (min)":     round(duration_secs / 60, 1),
                f"Session pts ({plan_tier})":  s_pts_str,
                f"Exposure pts ({plan_tier})": e_pts_str,
                "Session rate (pts/hr)":       session_rate  if session_rate  is not None else "n/a",
                "Exposure rate (pts/hr)":      exposure_rate if exposure_rate is not None else "n/a",
                "File":               str(filename),
            }
            plan_log.append(log_entry)
            total_plans += 1

    # Write summary CSV
    summary_path = output_dir / f"plan_summary_{args.season}.csv"
    pd.DataFrame(plan_log).to_csv(summary_path, index=False)

    print(f"\n  {'-'*84}")
    print(f"  {'TOTALS':<40} {total_plans:>7} plans  "
          f"{format_duration(total_duration_s):>10} "
          f"{total_session_pts:>11.0f} pts "
          f"{total_exposure_pts:>12.0f} pts")

    print(f"\n{'='*60}")
    print(f"  Done! {total_plans} plan files written to: {output_dir}/")
    print(f"  Summary CSV: {summary_path}")
    print(f"{'='*60}\n")

    print("Telescope assignment summary:")
    print(targets.groupby("Assigned_Telescope").size().rename("Targets").to_string())
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate iTelescope ACP observing plans for the Arp catalog.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--season", default="Spring",
        choices=list(SEASON_SHEETS.keys()),
        help="Which season's targets to generate plans for (default: Spring)"
    )
    parser.add_argument(
        "--telescope", default=None,
        help="Force a specific telescope (e.g. T11). Omit for auto-assignment."
    )
    parser.add_argument(
        "--output-dir", default="acp_plans",
        help="Directory to write plan files into (default: acp_plans/)"
    )
    parser.add_argument(
        "--targets-per-plan", type=int, default=5,
        metavar="N",
        help="Number of targets to include per plan file (default: 5)"
    )
    parser.add_argument(
        "--exposure", type=int, default=300,
        choices=[60, 120, 180, 300, 600],
        metavar="SECONDS",
        help="Sub-exposure duration in seconds: 60/120/180/300/600 (default: 300)"
    )
    parser.add_argument(
        "--count", type=int, default=2,
        metavar="N",
        help="Number of exposures per filter per repeat cycle for Luminance (default: 2, use with --repeat 3)"
    )
    parser.add_argument(
        "--binning", type=int, default=1, choices=[1, 2],
        help="CCD binning: 1 or 2 (default: 1)"
    )
    parser.add_argument(
        "--repeat", type=int, default=3,
        metavar="N",
        help="ACP #REPEAT value — cycles through all filters this many times (default: 3)"
    )
    parser.add_argument(
        "--plan-tier", default="Plan-40",
        choices=PLAN_TIERS,
        help="iTelescope membership plan tier for cost estimation (default: Plan-40)"
    )
    parser.add_argument(
        "--no-adaptive", action="store_true",
        help="Add #FORCESTARTUP + #NOADAPTIVE to disable adaptive focusing"
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
