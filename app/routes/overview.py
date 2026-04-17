from flask import Blueprint, render_template
from sqlalchemy import func

from app import db
from app.models import ImagingLog, MoonCalendarRun, Target

bp = Blueprint("overview", __name__)


@bp.route("/")
def index():
    total = db.session.query(func.count(Target.id)).scalar()
    done = (
        db.session.query(func.count(Target.id))
        .filter(Target.status == "Done")
        .scalar()
    )
    remaining = total - done
    log_count = db.session.query(func.count(ImagingLog.id)).scalar()
    total_exposure = db.session.query(
        func.coalesce(func.sum(ImagingLog.exposure_minutes), 0)
    ).scalar()

    seasons = (
        db.session.query(
            Target.season,
            func.count(Target.id).label("total"),
            func.count(Target.id).filter(Target.status == "Done").label("done"),
        )
        .group_by(Target.season)
        .all()
    )

    season_progress = []
    for s in seasons:
        pct = round(s.done / s.total * 100) if s.total > 0 else 0
        season_progress.append(
            {"name": s.season, "total": s.total, "done": s.done, "pct": pct}
        )

    moon_run = (
        db.session.query(MoonCalendarRun)
        .filter_by(status="complete")
        .order_by(MoonCalendarRun.generated_at.desc())
        .first()
    )

    phase_calendar = moon_run.phase_calendar if moon_run else []

    reimage = (
        db.session.query(ImagingLog)
        .filter(ImagingLog.quality <= 2)
        .order_by(ImagingLog.date_imaged.desc())
        .limit(20)
        .all()
    )

    return render_template(
        "overview.html",
        total=total,
        done=done,
        remaining=remaining,
        log_count=log_count,
        total_exposure=total_exposure,
        season_progress=season_progress,
        phase_calendar=phase_calendar[:60],
        reimage=reimage,
        done_pct=round(done / total * 100) if total > 0 else 0,
    )
