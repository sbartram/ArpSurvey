"""
ACP plan generation service.

Extracted from arp_acp_generator.py. Generates iTelescope ACP-format
observing plans from target data.
"""

from arp_common import (
    TELESCOPE_TIERS, SITE_TELESCOPES, LRGB_FILTERS, LUM_FILTERS,
    OVERHEAD_PER_TARGET_SECS, OVERHEAD_SESSION_SECS,
    sanitize_name,
)


def compute_lrgb_counts(count):
    """Compute per-filter exposure counts for LRGB from the luminance count."""
    return [count, max(1, count // 2), max(1, count // 2), max(1, count // 2)]


def parse_fov(telescope_row):
    """Return FOV in arcminutes, or None."""
    try:
        x = float(telescope_row["FOV X (arcmins)"])
        y = float(telescope_row["FOV Y (arcmins)"])
        return min(x, y)
    except (ValueError, TypeError, KeyError):
        return None


def assign_telescope(size_arcmin, site_key, telescopes_df, preferred_telescope=None):
    """
    Determine the best telescope for a target.

    Args:
        size_arcmin: Target angular size
        site_key: Observatory site string (e.g. "Utah Desert Remote Observatory")
        telescopes_df: DataFrame from load_telescopes(), indexed by telescope ID
        preferred_telescope: Force a specific telescope if valid

    Returns telescope ID string.
    """
    if preferred_telescope and preferred_telescope in telescopes_df.index:
        return preferred_telescope

    candidates = []
    for min_s, max_s, tel_ids in TELESCOPE_TIERS:
        if min_s <= size_arcmin < max_s:
            candidates = tel_ids
            break

    site_preferred = []
    for sk, site_tels in SITE_TELESCOPES.items():
        if sk.lower() in site_key.lower():
            site_preferred.extend(site_tels)

    ordered = ([t for t in candidates if t in site_preferred] +
               [t for t in candidates if t not in site_preferred])

    for tel_id in ordered:
        if tel_id not in telescopes_df.index:
            continue
        fov = parse_fov(telescopes_df.loc[tel_id])
        if fov and size_arcmin * 1.5 <= fov:
            return tel_id

    for tel_id in candidates:
        if tel_id in telescopes_df.index:
            return tel_id

    return "T11"


def format_duration(total_secs):
    """Return human-readable duration string."""
    h = int(total_secs // 3600)
    m = int((total_secs % 3600) // 60)
    return f"{h}h {m:02d}m" if h > 0 else f"{m}m"


def build_plan(targets, telescope_id, observatory, params, filename=None,
               date_str=None, cost_points=None):
    """
    Generate an ACP plan from target data.

    Args:
        targets: List of dicts with keys: arp, name, ra_hours, dec_degrees,
                 size_arcmin, filter_strategy, magnitude (optional),
                 transit_local, hours, moon (optional — for session plans)
        telescope_id: Telescope string ID (e.g. "T20")
        observatory: Observatory name (e.g. "Utah Desert Remote Observatory")
        params: Dict with keys: exposure, count, repeat, plan_tier, binning
        filename: Plan filename for the header (optional)
        date_str: Observation date string for the header (optional)
        cost_points: Estimated cost in points (optional)

    Returns dict: {filename, content, duration_secs, cost_points}
    """
    from datetime import datetime, timezone

    exposure = params["exposure"]
    count = params["count"]
    repeat = params["repeat"]
    plan_tier = params.get("plan_tier", "Plan-40")

    lrgb_counts = compute_lrgb_counts(count)
    lum_counts = [count]

    plan_name = filename or f"Arp_{observatory}_{telescope_id}_batch01"

    exposure_secs = 0
    for t in targets:
        strategy = t.get("filter_strategy", "Luminance")
        if strategy == "LRGB":
            exposure_secs += sum(lrgb_counts) * exposure
        else:
            exposure_secs += sum(lum_counts) * exposure

    imaging_secs = exposure_secs * repeat
    target_overhead = len(targets) * OVERHEAD_PER_TARGET_SECS
    total_secs = (exposure_secs + target_overhead) * repeat + OVERHEAD_SESSION_SECS

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = []
    lines.append(f"; ============================================================")
    lines.append(f"; Arp Catalog Nightly Session Plan")
    if date_str:
        lines.append(f"; Date        : {date_str}")
    lines.append(f"; Observatory : {observatory}")
    lines.append(f"; Telescope   : {telescope_id}")
    lines.append(f"; Targets     : {len(targets)}")
    lines.append(f"; Imaging time : {format_duration(imaging_secs)}  (shutter-open only)")
    lines.append(f"; Total duration: {format_duration(total_secs)}  (imaging + slew/overhead)")
    if cost_points is not None:
        lines.append(f"; Est. cost    : ~{cost_points:,.0f} pts (session billing, {plan_tier})")
    lines.append(f"; Plan tier    : {plan_tier}")
    lines.append(f"; Generated    : ArpSurvey Server on {now_str}")
    lines.append(f"; ============================================================")
    lines.append("")
    lines.append("#BillingMethod Session")
    lines.append("#RESUME")
    lines.append("#FIRSTLAST")
    lines.append(f"#repeat {repeat}")
    lines.append("")

    for t in targets:
        arp = t["arp"]
        name = sanitize_name(f"Arp{int(arp):03d}_{t['name']}")
        ra = t["ra_hours"]
        dec = t["dec_degrees"]
        size = t.get("size_arcmin", "?")
        strategy = t.get("filter_strategy", "Luminance")

        if strategy == "LRGB":
            filters = ",".join(LRGB_FILTERS)
            counts = ",".join(str(c) for c in lrgb_counts)
            intervals = ",".join(str(exposure) for _ in lrgb_counts)
            binnings = "1,2,2,2"
        else:
            filters = LUM_FILTERS[0]
            counts = str(lum_counts[0])
            intervals = str(exposure)
            binnings = "1"

        mag = t.get("magnitude")
        mag_str = f", mag: {mag}" if mag else ""
        transit_str = t.get("transit_local", "")
        hours = t.get("hours", "")
        moon = t.get("moon", {})
        if transit_str and hours:
            moon_phase = moon.get("phase_pct", "")
            moon_sep = moon.get("separation_deg", "")
            peak_el = t.get("peak_elevation", "")
            el_str = f", el {peak_el}deg" if peak_el else ""
            window_str = f"  [{hours}h window, transit {transit_str}{el_str}, moon {moon_phase}% sep {moon_sep}deg]"
        else:
            window_str = ""
        lines.append(f"; --- Arp {arp}: {t['name']}  (size: {size}'{mag_str}){window_str} ---")
        lines.append(f"#count {counts}")
        lines.append(f"#interval {intervals}")
        lines.append(f"#binning {binnings}")
        lines.append(f"#filter {filters}")
        lines.append(f"{name}\t{ra:.6f}\t{dec:.6f}")
        lines.append("")

    lines.append("#shutdown")

    return {
        "filename": f"{plan_name}.txt",
        "content": "\n".join(lines),
        "duration_secs": total_secs,
        "cost_points": None,
    }
