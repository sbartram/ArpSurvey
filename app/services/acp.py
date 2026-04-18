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
        site_key: Observatory site string (e.g. "New Mexico / Spain" or "Spain")
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


def build_plan(targets, telescope_id, season, params, filename=None):
    """
    Generate an ACP plan from target data.

    Args:
        targets: List of dicts with keys: arp, name, ra_hours, dec_degrees,
                 size_arcmin, filter_strategy, magnitude (optional)
        telescope_id: Telescope string ID (e.g. "T20")
        season: Season name
        params: Dict with keys: exposure, count, repeat, plan_tier, binning
        filename: Plan filename for the header (optional)

    Returns dict: {filename, content, duration_secs, cost_points}
    """
    from datetime import datetime, timezone

    exposure = params["exposure"]
    count = params["count"]
    repeat = params["repeat"]
    plan_tier = params.get("plan_tier", "Plan-40")

    lrgb_counts = compute_lrgb_counts(count)
    lum_counts = [count]

    plan_name = filename or f"Arp_{season}_{telescope_id}_batch01"

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
    lines.append(f"; Arp Catalog Observing Plan")
    lines.append(f"; Plan Name    : {plan_name}")
    lines.append(f"; Telescope    : {telescope_id}")
    lines.append(f"; Season       : {season}")
    lines.append(f"; Targets      : {len(targets)}")
    lines.append(f"; Imaging time : {format_duration(imaging_secs)}")
    lines.append(f"; Total duration: {format_duration(total_secs)}")
    lines.append(f"; Generated    : Arp ACP Generator on {now_str}")
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
        lines.append(f"; --- Arp {arp}: {t['name']}  (size: {size}'{mag_str}) ---")
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
