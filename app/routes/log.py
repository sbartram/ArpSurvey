import csv
import io
from datetime import date

from flask import Blueprint, render_template, request, Response
from sqlalchemy import func

from app import db
from app.models import Target, Telescope, ImagingLog

bp = Blueprint("log", __name__)


@bp.route("/log")
def index():
    logs = db.session.query(ImagingLog).order_by(ImagingLog.date_imaged.desc()).all()
    targets = db.session.query(Target).order_by(Target.arp_number).all()
    telescopes = db.session.query(Telescope).order_by(Telescope.telescope_id).all()

    stats = _compute_stats()

    return render_template("log.html", logs=logs, targets=targets,
                           telescopes=telescopes, stats=stats,
                           today=date.today().isoformat())


@bp.route("/log", methods=["POST"])
def create():
    arp_number = request.form.get("arp_number", type=int)
    target = db.session.query(Target).filter_by(arp_number=arp_number).first()
    if not target:
        return '<div class="card" style="border-left:3px solid var(--red)">Target not found</div>', 400

    telescope_id_str = request.form.get("telescope")
    telescope = db.session.query(Telescope).filter_by(telescope_id=telescope_id_str).first()

    log = ImagingLog(
        target_id=target.id,
        date_imaged=request.form.get("date") or date.today(),
        telescope_id=telescope.id if telescope else None,
        filter_strategy=request.form.get("filter_strategy", "Luminance"),
        exposure_minutes=request.form.get("exposure", type=float),
        quality=request.form.get("quality", 3, type=int),
        notes=request.form.get("notes", "").strip(),
    )
    db.session.add(log)

    # Auto-set target status to Done if first observation
    if target.status == "Pending" or target.status == "Scheduled":
        target.status = "Done"

    db.session.commit()

    logs = db.session.query(ImagingLog).order_by(ImagingLog.date_imaged.desc()).all()
    stats = _compute_stats()

    return render_template("partials/log_table.html", logs=logs) + \
           render_template("partials/log_stats.html", stats=stats)


@bp.route("/log/<int:log_id>", methods=["DELETE"])
def delete(log_id):
    log = db.session.get(ImagingLog, log_id)
    if log:
        db.session.delete(log)
        db.session.commit()

    logs = db.session.query(ImagingLog).order_by(ImagingLog.date_imaged.desc()).all()
    stats = _compute_stats()

    return render_template("partials/log_table.html", logs=logs) + \
           render_template("partials/log_stats.html", stats=stats)


@bp.route("/log/export")
def export_csv():
    logs = db.session.query(ImagingLog).order_by(ImagingLog.date_imaged.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Arp #", "Name", "Telescope", "Filters",
                     "Exposure (min)", "Quality", "Notes"])
    for log in logs:
        writer.writerow([
            log.date_imaged, log.target.arp_number, log.target.name,
            log.telescope.telescope_id if log.telescope else "",
            log.filter_strategy, log.exposure_minutes, log.quality, log.notes
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=imaging_log.csv"}
    )


def _compute_stats():
    total_logs = db.session.query(func.count(ImagingLog.id)).scalar()
    total_exposure = db.session.query(
        func.coalesce(func.sum(ImagingLog.exposure_minutes), 0)
    ).scalar()
    unique_targets = db.session.query(
        func.count(func.distinct(ImagingLog.target_id))
    ).scalar()
    avg_quality = db.session.query(
        func.avg(ImagingLog.quality)
    ).scalar()

    return {
        "total_logs": total_logs,
        "total_exposure_hrs": round(total_exposure / 60, 1) if total_exposure else 0,
        "unique_targets": unique_targets,
        "avg_quality": round(avg_quality, 1) if avg_quality else 0,
    }
