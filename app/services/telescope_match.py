"""
Telescope match service.

Evaluates and ranks telescopes for a specific target on a given date.
Computes visibility, SNR, FOV fit, cost, and a composite quality score.
"""

import math

from app.services.astronomy import dark_window, target_visibility, alt_at_time
from app.services.snr import estimate_snr


DEFAULT_SNR_TARGET = 30
DEFAULT_PLAN_TIER = "Plan-40"
DEFAULT_MIN_ELEVATION = 30
DEFAULT_EXPOSURE_SECS = 300

SCORE_WEIGHTS = {
    "time_to_snr": 0.35,
    "fov_fit": 0.20,
    "hours": 0.20,
    "elevation": 0.15,
    "cost": 0.10,
}


def evaluate_telescope(target, telescope, date, site_key, moon_info,
                       snr_target=DEFAULT_SNR_TARGET, plan_tier=DEFAULT_PLAN_TIER):
    """
    Compute all comparison metrics for one target+telescope+date.

    Args:
        target: dict with keys arp_number, name, ra_hours, dec_degrees,
                size_arcmin, magnitude, filter_strategy
        telescope: Telescope model instance
        date: observation date (datetime.date)
        site_key: observatory name matching telescope.site
        moon_info: dict with phase_pct, separation_deg, risk
        snr_target: desired SNR goal (default 30)
        plan_tier: billing plan tier (default "Plan-40")

    Returns dict with all metrics plus disqualified/disqualification_reason.
    """
    ra_h = target["ra_hours"]
    dec_deg = target["dec_degrees"]
    size = target.get("size_arcmin") or 1.0
    mag = target.get("magnitude")
    strategy = target.get("filter_strategy", "Luminance")

    base = {
        "telescope_id": telescope.telescope_id,
        "site": telescope.site,
        "aperture_mm": telescope.aperture_mm,
    }

    # --- Disqualification: unknown site ---
    from arp_common import OBSERVATORIES
    if site_key not in OBSERVATORIES:
        return {**base, "disqualified": True,
                "disqualification_reason": f"Unknown site: {site_key}"}

    # --- Disqualification: target visibility ---
    eve_dt, morn_dt = dark_window(site_key, date)
    vis = target_visibility(ra_h, dec_deg, site_key, eve_dt, morn_dt)

    if not vis or vis["hours"] <= 0:
        return {**base, "disqualified": True,
                "disqualification_reason": f"Target never above {DEFAULT_MIN_ELEVATION}\u00b0 during dark window"}

    peak_el = round(alt_at_time(ra_h, dec_deg, site_key, vis["transit"]), 1)
    hours = vis["hours"]
    airmass = round(1.0 / math.sin(math.radians(max(peak_el, 10))), 2)

    # --- Disqualification: FOV ---
    fov = telescope.fov_arcmin or 60.0
    fov_fill_pct = round(size / fov * 100, 1)

    if fov_fill_pct > 100:
        return {**base, "disqualified": True,
                "disqualification_reason": f"Target ({size:.1f}') exceeds telescope FOV ({fov:.0f}')"}

    # --- Disqualification: filters ---
    tel_filters = set(telescope.filters or [])
    required = _required_filters(strategy)
    missing = required - tel_filters
    if missing:
        return {**base, "disqualified": True,
                "disqualification_reason": f"Missing filter(s): {', '.join(sorted(missing))}"}

    # --- Disqualification: no magnitude ---
    if mag is None:
        return {**base, "disqualified": True,
                "disqualification_reason": "No magnitude data for SNR calculation"}

    # --- Metrics ---
    resolution = telescope.resolution or 1.0
    target_pixels = round(size * 60 / resolution)

    snr_result = estimate_snr(
        target_mag=mag,
        target_size_arcmin=size,
        telescope=telescope,
        site_key=site_key,
        elevation_deg=peak_el,
        moon_phase_pct=moon_info["phase_pct"],
        moon_sep_deg=moon_info["separation_deg"],
    )

    if not snr_result or snr_result["snr_single"] <= 0:
        return {**base, "disqualified": True,
                "disqualification_reason": "Could not compute SNR (insufficient telescope specs)"}

    snr_single = snr_result["snr_single"]
    n_subs = math.ceil((snr_target / snr_single) ** 2) if snr_single < snr_target else 1
    time_to_snr_secs = n_subs * DEFAULT_EXPOSURE_SECS
    time_to_snr_minutes = round(time_to_snr_secs / 60, 1)

    # Cost from exposure rate
    rate = telescope.rates.filter_by(plan_tier=plan_tier).first()
    exposure_rate = rate.exposure_rate if rate else 0
    cost_points = round(time_to_snr_minutes / 60 * exposure_rate, 1)

    return {
        **base,
        "disqualified": False,
        "disqualification_reason": None,
        "peak_elevation": peak_el,
        "hours": hours,
        "airmass": airmass,
        "target_pixels": target_pixels,
        "fov_fill_pct": fov_fill_pct,
        "snr_single": snr_single,
        "n_subs": n_subs,
        "time_to_snr_minutes": time_to_snr_minutes,
        "cost_points": cost_points,
        "moon_risk": moon_info["risk"],
        "effective_sky_mag": snr_result["effective_sky_mag"],
    }


def _required_filters(strategy):
    """Return the set of filter letters required for a given strategy."""
    s = strategy.upper() if strategy else "L"
    if "LRGB" in s:
        return {"L", "R", "G", "B"}
    if "HA" in s or "NARROWBAND" in s:
        return {"Ha"}
    return {"L"}


def compare_telescopes(target, date, moon_info, snr_target=DEFAULT_SNR_TARGET,
                       plan_tier=DEFAULT_PLAN_TIER):
    """
    Evaluate all telescopes in the DB for a target+date.

    Args:
        target: dict with arp_number, name, ra_hours, dec_degrees,
                size_arcmin, magnitude, filter_strategy
        date: observation date (datetime.date)
        moon_info: dict with phase_pct, separation_deg, risk
        snr_target: desired SNR goal
        plan_tier: billing tier for cost calculation

    Returns dict: {"viable": [...], "excluded": [...]}
        viable: sorted by composite score descending
        excluded: sorted by telescope_id
    """
    from app.models import Telescope

    telescopes = Telescope.query.filter_by(active=True).all()

    viable = []
    excluded = []

    for tel in telescopes:
        result = evaluate_telescope(
            target=target, telescope=tel, date=date,
            site_key=tel.site, moon_info=moon_info,
            snr_target=snr_target, plan_tier=plan_tier,
        )
        if result["disqualified"]:
            excluded.append(result)
        else:
            viable.append(result)

    _compute_scores(viable)

    viable.sort(key=lambda r: r.get("score", 0), reverse=True)
    excluded.sort(key=lambda r: r.get("telescope_id", ""))

    return {"viable": viable, "excluded": excluded}


def _compute_scores(viable):
    """Compute composite quality scores using min-max normalization."""
    if not viable:
        return

    if len(viable) == 1:
        viable[0]["score"] = 75  # single option gets a decent score
        return

    # Extract raw values for min-max normalization
    times = [r["time_to_snr_minutes"] for r in viable]
    hours = [r["hours"] for r in viable]
    elevs = [r["peak_elevation"] for r in viable]
    costs = [r["cost_points"] for r in viable]

    for r in viable:
        # Time to SNR: lower is better -> invert
        t_norm = 1.0 - _min_max_norm(r["time_to_snr_minutes"], times)

        # FOV fill: optimal 10-60%, penalize outside
        f_norm = _fov_fit_score(r["fov_fill_pct"])

        # Hours: higher is better
        h_norm = _min_max_norm(r["hours"], hours)

        # Elevation: higher is better
        e_norm = _min_max_norm(r["peak_elevation"], elevs)

        # Cost: lower is better -> invert
        c_norm = 1.0 - _min_max_norm(r["cost_points"], costs)

        raw = (SCORE_WEIGHTS["time_to_snr"] * t_norm +
               SCORE_WEIGHTS["fov_fit"] * f_norm +
               SCORE_WEIGHTS["hours"] * h_norm +
               SCORE_WEIGHTS["elevation"] * e_norm +
               SCORE_WEIGHTS["cost"] * c_norm)

        r["score"] = round(raw * 100, 1)


def _min_max_norm(value, values):
    """Normalize value to 0-1 range within values. Returns 0.5 if all equal."""
    lo, hi = min(values), max(values)
    if hi == lo:
        return 0.5
    return (value - lo) / (hi - lo)


def _fov_fit_score(fill_pct):
    """Score FOV fill percentage. Optimal range 10-60%, penalized outside."""
    if fill_pct <= 0:
        return 0.0
    if fill_pct <= 10:
        return fill_pct / 10.0 * 0.7   # ramp up to 0.7 at 10%
    if fill_pct <= 60:
        return 0.7 + (fill_pct - 10) / 50.0 * 0.3  # 0.7 to 1.0
    if fill_pct <= 100:
        return 1.0 - (fill_pct - 60) / 40.0 * 0.8  # 1.0 down to 0.2
    return 0.0  # clipped
