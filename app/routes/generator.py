from flask import Blueprint, render_template, request
from arp_common import SEASON_SHEETS, PLAN_TIERS, SITE_TELESCOPES, load_telescopes
from app import db
from app.models import Target, Telescope, GeneratedPlan
from app.services.acp import assign_telescope, build_plan

bp = Blueprint("generator", __name__)


@bp.route("/generator")
def index():
    seasons = [s for s in SEASON_SHEETS.keys() if s != "All"]
    telescopes = db.session.query(Telescope).order_by(Telescope.telescope_id).all()
    plans = db.session.query(GeneratedPlan).order_by(
        GeneratedPlan.created_at.desc()
    ).limit(20).all()
    return render_template("generator.html", seasons=seasons,
                           telescopes=telescopes, plan_tiers=PLAN_TIERS, plans=plans)


@bp.route("/generator/run", methods=["POST"])
def run():
    season = request.form.get("season", "Spring")
    telescope_override = request.form.get("telescope", "").strip() or None
    exposure = request.form.get("exposure", 300, type=int)
    count = request.form.get("count", 2, type=int)
    repeat = request.form.get("repeat", 3, type=int)
    plan_tier = request.form.get("plan_tier", "Plan-40")
    targets_per_plan = request.form.get("targets_per_plan", 5, type=int)

    # Load targets for season
    targets = db.session.query(Target).filter(Target.season == season).all()
    if not targets:
        return '<div class="card" style="border-left:3px solid var(--red)">No targets found for this season.</div>'

    # Load telescope data for assignment
    tels_df = load_telescopes()

    # Group targets by assigned telescope
    target_groups = {}
    for t in targets:
        size = t.size_arcmin or 3.0
        site = t.best_site or "Any site"
        tel_id = assign_telescope(size, site, tels_df, preferred_telescope=telescope_override)
        target_groups.setdefault(tel_id, []).append(t)

    params = {"exposure": exposure, "count": count, "repeat": repeat,
              "plan_tier": plan_tier, "binning": 1}

    generated = []
    for tel_id, group in target_groups.items():
        # Split into batches
        for i in range(0, len(group), targets_per_plan):
            batch = group[i:i + targets_per_plan]
            batch_num = i // targets_per_plan + 1

            target_dicts = [{
                "arp": t.arp_number, "name": t.name,
                "ra_hours": t.best_ra, "dec_degrees": t.best_dec,
                "size_arcmin": t.size_arcmin, "filter_strategy": t.filter_strategy,
            } for t in batch]

            filename = f"Arp_{season}_{tel_id}_batch{batch_num:02d}.txt"
            # Determine observatory from telescope
            obs_name = next(
                (site for site, tels in SITE_TELESCOPES.items() if tel_id in tels),
                "Unknown"
            )
            result = build_plan(target_dicts, tel_id, obs_name, params, filename=filename)

            # Look up telescope DB record for FK
            tel_record = db.session.query(Telescope).filter_by(telescope_id=tel_id).first()

            plan = GeneratedPlan(
                filename=filename,
                plan_type="acp",
                content=result["content"],
                season=season,
                telescope_id=tel_record.id if tel_record else None,
                metadata_=params,
            )
            db.session.add(plan)
            generated.append({"filename": filename, "targets": len(batch),
                              "telescope": tel_id})

    db.session.commit()

    return render_template("partials/plan_list.html", generated=generated,
                           season=season, total=len(targets))
