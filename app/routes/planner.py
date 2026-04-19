import datetime

from flask import Blueprint, render_template, request
from arp_common import OBSERVATORIES, load_telescopes

from app import db
from app.models import Target, SessionResult, GeneratedPlan, Telescope
from app.services.session import compute_session
from app.services.astronomy import dark_window
from app.services.acp import build_plan, assign_telescope
from app.services.snr import estimate_snr, snr_quality_label
from app.services.telescope_match import compare_telescopes, DEFAULT_SNR_TARGET
from app.services.astronomy import build_observer, moon_info as compute_moon_info

bp = Blueprint("planner", __name__)


@bp.route("/planner")
def index():
    sites = list(OBSERVATORIES.keys())
    last_session = db.session.query(SessionResult).order_by(
        SessionResult.computed_at.desc()
    ).first()
    return render_template(
        "planner.html",
        sites=sites,
        last_session=last_session,
        today=datetime.date.today().isoformat(),
    )


@bp.route("/planner/compute", methods=["POST"])
def compute():
    date_str = request.form.get("date") or datetime.date.today().isoformat()
    site_key = request.form.get("site", "New Mexico")
    min_hours = request.form.get("min_hours", 1.5, type=float)
    moon_filter = request.form.get("moon_filter", "")

    obs_date = datetime.date.fromisoformat(date_str)

    targets = db.session.query(Target).all()
    target_dicts = [{
        "arp_number": t.arp_number, "name": t.name,
        "ra_hours": t.best_ra, "dec_degrees": t.best_dec,
        "size_arcmin": t.size_arcmin, "filter_strategy": t.filter_strategy,
        "best_site": t.best_site,
    } for t in targets]

    results = compute_session(obs_date, site_key, target_dicts, min_hours, moon_filter)

    # Assign telescopes and estimate SNR for each result
    tels_df = load_telescopes()
    # Build magnitude lookup from DB targets
    mag_lookup = {t.arp_number: t.magnitude for t in targets}

    for r in results:
        size = r.get("size_arcmin") or 3.0
        tel_id = assign_telescope(size, site_key, tels_df)
        r["telescope"] = tel_id
        r["magnitude"] = mag_lookup.get(r["arp"])

        # SNR estimation
        tel_record = db.session.query(Telescope).filter_by(telescope_id=tel_id).first()
        if tel_record and r.get("magnitude") and r.get("peak_elevation"):
            snr_result = estimate_snr(
                target_mag=r["magnitude"],
                target_size_arcmin=size,
                telescope=tel_record,
                site_key=site_key,
                elevation_deg=r["peak_elevation"],
                moon_phase_pct=r["moon"]["phase_pct"],
                moon_sep_deg=r["moon"]["separation_deg"],
                exposure_secs=300,
                n_subs=6,  # typical: 2 per repeat × 3 repeats
            )
            if snr_result:
                r["snr"] = snr_result["snr_total"]
                r["snr_quality"] = snr_quality_label(snr_result["snr_total"])
            else:
                r["snr"] = None
                r["snr_quality"] = "?"
        else:
            r["snr"] = None
            r["snr_quality"] = "?"

    # Dark window for display
    eve_dt, morn_dt = dark_window(site_key, obs_date)
    utc_offset = OBSERVATORIES[site_key]["utc_offset"]
    eve_local = (eve_dt + datetime.timedelta(hours=utc_offset)).strftime("%H:%M")
    morn_local = (morn_dt + datetime.timedelta(hours=utc_offset)).strftime("%H:%M")
    dark_hrs = round((morn_dt - eve_dt).total_seconds() / 3600, 1)

    # Target status lookup
    status_lookup = {t.arp_number: {"status": t.status, "id": t.id} for t in targets}
    for r in results:
        info = status_lookup.get(r["arp"], {})
        r["target_status"] = info.get("status", "Pending")
        r["target_id"] = info.get("id")

    # Store session results
    session_result = SessionResult(
        site_key=site_key,
        date_local=obs_date,
        eve_twilight=eve_dt,
        morn_twilight=morn_dt,
        results=results,
    )
    db.session.add(session_result)
    db.session.commit()

    # Collect unique telescopes and filter strategies for filter dropdowns
    telescopes = sorted(set(r["telescope"] for r in results))
    strategies = sorted(set(r["filter_strategy"] for r in results))

    summary = {
        "date": date_str, "site": site_key,
        "eve_local": eve_local, "morn_local": morn_local,
        "dark_hrs": dark_hrs, "total": len(results),
        "good": sum(1 for r in results if r["moon"]["risk"] == "G"),
        "marginal": sum(1 for r in results if r["moon"]["risk"] == "M"),
        "avoid": sum(1 for r in results if r["moon"]["risk"] == "A"),
    }

    return render_template("partials/planner_table.html",
                           results=results, summary=summary,
                           telescopes=telescopes, strategies=strategies,
                           date=date_str, site=site_key)


@bp.route("/planner/filter")
def filter_planner():
    last = db.session.query(SessionResult).order_by(
        SessionResult.computed_at.desc()
    ).first()
    if not last or not last.results:
        return '<div class="empty-state">No session data.</div>'

    results = list(last.results)

    # Apply filters
    search = request.args.get("search", "").strip().lower()
    telescope = request.args.get("telescope", "")
    strategy = request.args.get("strategy", "")
    sort_by = request.args.get("sort", "transit")
    hide_done = request.args.get("hide_done", "") == "on"

    if search:
        results = [r for r in results
                   if search in str(r["arp"]) or search in r["name"].lower()]
    if telescope:
        results = [r for r in results if r.get("telescope") == telescope]
    if strategy:
        results = [r for r in results if r.get("filter_strategy") == strategy]
    if hide_done:
        results = [r for r in results if r.get("target_status") != "Done"]

    # Sort
    sort_keys = {
        "arp": lambda r: r["arp"],
        "name": lambda r: r["name"].lower(),
        "transit": lambda r: r["transit"],
        "hours": lambda r: r["hours"],
        "elevation": lambda r: r.get("peak_elevation", 0),
        "moon": lambda r: r["moon"]["phase_pct"],
        "sep": lambda r: r["moon"]["separation_deg"],
        "risk": lambda r: {"G": 0, "M": 1, "A": 2}.get(r["moon"]["risk"], 3),
        "telescope": lambda r: r.get("telescope", ""),
        "filters": lambda r: r.get("filter_strategy", ""),
        "snr": lambda r: r.get("snr") or 0,
        "status": lambda r: r.get("target_status", ""),
    }
    reverse = sort_by.startswith("-")
    sort_field = sort_by.lstrip("-")
    key_fn = sort_keys.get(sort_field, sort_keys["transit"])
    results.sort(key=key_fn, reverse=reverse)

    return render_template("partials/planner_rows.html", results=results,
                           date=last.date_local.isoformat(), site=last.site_key)


@bp.route("/planner/compare")
def compare():
    arp_num = request.args.get("arp", type=int)
    date_str = request.args.get("date") or datetime.date.today().isoformat()
    site_key = request.args.get("site", "New Mexico") or "New Mexico"
    snr_target = request.args.get("snr_target", DEFAULT_SNR_TARGET, type=float)
    sort_by = request.args.get("sort", "score")
    sort_dir = request.args.get("dir", "desc")

    if arp_num is None:
        return '<div class="empty-state">No target specified.</div>'

    target_record = db.session.query(Target).filter_by(
        arp_number=arp_num
    ).first()
    if not target_record:
        return '<div class="empty-state">Target not found.</div>'

    obs_date = datetime.date.fromisoformat(date_str)

    target = {
        "arp_number": target_record.arp_number,
        "name": target_record.name,
        "ra_hours": target_record.best_ra,
        "dec_degrees": target_record.best_dec,
        "size_arcmin": target_record.size_arcmin,
        "magnitude": target_record.magnitude,
        "filter_strategy": target_record.filter_strategy,
    }

    # Compute moon info for this target on this date
    obs = build_observer(site_key, obs_date)
    mi = compute_moon_info(target["ra_hours"], target["dec_degrees"], obs)

    result = compare_telescopes(
        target=target, date=obs_date, moon_info=mi,
        snr_target=snr_target,
    )

    # Apply column sort to viable list
    if sort_by != "score":
        reverse = sort_dir == "desc"
        sort_keys = {
            "telescope": lambda r: r.get("telescope_id", ""),
            "site": lambda r: r.get("site", ""),
            "elevation": lambda r: r.get("peak_elevation", 0),
            "hours": lambda r: r.get("hours", 0),
            "airmass": lambda r: r.get("airmass", 99),
            "pixels": lambda r: r.get("target_pixels", 0),
            "fov": lambda r: r.get("fov_fill_pct", 0),
            "snr": lambda r: r.get("snr_single", 0),
            "time": lambda r: r.get("time_to_snr_minutes", 9999),
            "cost": lambda r: r.get("cost_points", 9999),
            "moon": lambda r: {"G": 0, "M": 1, "A": 2}.get(r.get("moon_risk", ""), 3),
        }
        key_fn = sort_keys.get(sort_by, lambda r: r.get("score", 0))
        result["viable"].sort(key=key_fn, reverse=reverse)

    return render_template("partials/telescope_compare.html",
                           target=target, date=date_str, site=site_key,
                           snr_target=snr_target,
                           target_id=target_record.id,
                           target_status=target_record.status,
                           preferred_telescope=target_record.preferred_telescope,
                           viable=result["viable"],
                           excluded=result["excluded"])


@bp.route("/planner/restore")
def restore():
    """Re-render the full planner table from the last SessionResult.

    Used by the compare view's "Back to targets" button, since the compare
    swap destroys #planner-filters and the filter route can't restore the
    full table layout.
    """
    last = db.session.query(SessionResult).order_by(
        SessionResult.computed_at.desc()
    ).first()
    if not last or not last.results:
        return '<div class="empty-state">No session data. Compute a session first.</div>'

    results = list(last.results)
    utc_offset = OBSERVATORIES[last.site_key]["utc_offset"]
    eve_local = (last.eve_twilight + datetime.timedelta(hours=utc_offset)).strftime("%H:%M")
    morn_local = (last.morn_twilight + datetime.timedelta(hours=utc_offset)).strftime("%H:%M")
    dark_hrs = round((last.morn_twilight - last.eve_twilight).total_seconds() / 3600, 1)

    telescopes = sorted(set(r["telescope"] for r in results))
    strategies = sorted(set(r["filter_strategy"] for r in results))

    summary = {
        "date": last.date_local.isoformat(), "site": last.site_key,
        "eve_local": eve_local, "morn_local": morn_local,
        "dark_hrs": dark_hrs, "total": len(results),
        "good": sum(1 for r in results if r["moon"]["risk"] == "G"),
        "marginal": sum(1 for r in results if r["moon"]["risk"] == "M"),
        "avoid": sum(1 for r in results if r["moon"]["risk"] == "A"),
    }

    return render_template("partials/planner_table.html",
                           results=results, summary=summary,
                           telescopes=telescopes, strategies=strategies,
                           date=last.date_local.isoformat(), site=last.site_key)


@bp.route("/planner/generate-acp", methods=["POST"])
def generate_acp():
    last = db.session.query(SessionResult).order_by(
        SessionResult.computed_at.desc()
    ).first()
    if not last or not last.results:
        return '<div class="empty-state">No session computed yet. Click "Compute session" first.</div>'

    tels_df = load_telescopes()
    site_key = last.site_key
    obs_date = last.date_local

    # Look up current target statuses and telescope preferences from DB
    targets_db = {t.arp_number: t for t in db.session.query(Target).all()}
    for r in last.results:
        t = targets_db.get(r["arp"])
        r["target_status"] = t.status if t else r.get("target_status", "Pending")

    scheduled = [r for r in last.results if r.get("target_status") == "Scheduled"]
    if not scheduled:
        return '<div class="empty-state">No targets marked as "Scheduled". Click a target\'s status badge to cycle it to Scheduled first.</div>'

    tel_groups = {}
    for r in scheduled:
        t = targets_db.get(r["arp"])
        preferred = t.preferred_telescope if t else None
        size = r.get("size_arcmin") or 3.0
        tel_id = preferred or r.get("telescope") or assign_telescope(size, site_key, tels_df)
        tel_groups.setdefault(tel_id, []).append(r)

    params = {"exposure": 300, "count": 2, "repeat": 3, "plan_tier": "Plan-40", "binning": 1}

    from arp_common import sanitize_name

    generated = []
    for tel_id, group in tel_groups.items():
        target_dicts = [{
            "arp": r["arp"], "name": r["name"],
            "ra_hours": r["ra_hours"], "dec_degrees": r["dec_degrees"],
            "size_arcmin": r.get("size_arcmin"),
            "filter_strategy": r.get("filter_strategy", "Luminance"),
            "magnitude": r.get("magnitude"),
            "transit_local": r.get("transit_local"),
            "hours": r.get("hours"),
            "peak_elevation": r.get("peak_elevation"),
            "moon": r.get("moon"),
        } for r in group]

        # Compute filename first so it appears in the plan header
        if len(group) == 1:
            target_name = sanitize_name(f"Arp{int(group[0]['arp']):03d}_{group[0]['name']}")
            filename = f"{target_name}-{tel_id}-{obs_date}.txt"
        else:
            filename = f"arp-session-{tel_id}-{obs_date}.txt"

        result = build_plan(target_dicts, tel_id, site_key, params,
                           filename=filename, date_str=str(obs_date))

        tel_record = db.session.query(Telescope).filter_by(telescope_id=tel_id).first()
        plan = GeneratedPlan(
            filename=filename, plan_type="session", content=result["content"],
            season="Session", telescope_id=tel_record.id if tel_record else None,
            metadata_=params,
        )
        db.session.add(plan)
        db.session.flush()
        generated.append({"filename": filename, "telescope": tel_id,
                          "targets": len(group), "plan_id": plan.id})

    db.session.commit()

    return render_template("partials/plan_list.html",
                           generated=generated, season="Session",
                           total=sum(g["targets"] for g in generated))
