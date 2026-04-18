import csv
import io
import json

from flask import Blueprint, render_template, Response
from sqlalchemy import func

from app import db
from app.models import Target, ImagingLog

bp = Blueprint("export", __name__)


@bp.route("/export")
def index():
    total = db.session.query(func.count(Target.id)).scalar()
    done = db.session.query(func.count(Target.id)).filter(Target.status == "Done").scalar()
    scheduled = db.session.query(func.count(Target.id)).filter(Target.status == "Scheduled").scalar()
    skipped = db.session.query(func.count(Target.id)).filter(Target.status == "Skip").scalar()

    seasons = db.session.query(
        Target.season,
        func.count(Target.id).label("total"),
        func.count(Target.id).filter(Target.status == "Done").label("done"),
    ).group_by(Target.season).all()

    season_data = []
    for s in seasons:
        pct = round(s.done / s.total * 100) if s.total > 0 else 0
        season_data.append({"name": s.season, "total": s.total, "done": s.done, "pct": pct})

    total_exposure = db.session.query(
        func.coalesce(func.sum(ImagingLog.exposure_minutes), 0)
    ).scalar()

    return render_template("export.html",
        total=total, done=done, scheduled=scheduled, skipped=skipped,
        remaining=total - done - skipped,
        done_pct=round(done / total * 100) if total > 0 else 0,
        season_data=season_data,
        total_exposure_hrs=round(total_exposure / 60, 1) if total_exposure else 0,
    )


@bp.route("/export/csv")
def export_csv():
    targets = db.session.query(Target).order_by(Target.arp_number).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Arp #", "Name", "Season", "Status", "RA (hours)", "Dec (deg)",
                     "Size (arcmin)", "Best Site", "Filter Strategy"])
    for t in targets:
        writer.writerow([t.arp_number, t.name, t.season, t.status,
                         round(t.best_ra, 6), round(t.best_dec, 6),
                         t.size_arcmin, t.best_site, t.filter_strategy])

    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=arp_targets.csv"})


@bp.route("/export/targets")
def export_targets():
    targets = db.session.query(Target).order_by(Target.arp_number).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Arp #", "Name", "RA (hours)", "Dec (deg)", "NED RA", "NED Dec",
                     "Size (arcmin)", "Season", "Best Site"])
    for t in targets:
        writer.writerow([t.arp_number, t.name, round(t.ra_hours, 6), round(t.dec_degrees, 6),
                         round(t.ned_ra_hours, 6) if t.ned_ra_hours else "",
                         round(t.ned_dec_degrees, 6) if t.ned_dec_degrees else "",
                         t.size_arcmin, t.season, t.best_site])

    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=arp_target_coords.csv"})


@bp.route("/export/status-json")
def export_status_json():
    targets = db.session.query(Target).order_by(Target.arp_number).all()
    data = {str(t.arp_number): t.status for t in targets}

    return Response(json.dumps(data, indent=2), mimetype="application/json",
                    headers={"Content-Disposition": "attachment; filename=arp_status.json"})
