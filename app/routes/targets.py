from flask import Blueprint, jsonify, render_template, request
from app import db
from app.models import Target, ImagingLog

bp = Blueprint("targets", __name__)

STATUS_CYCLE = {"Pending": "Scheduled", "Scheduled": "Done", "Done": "Skip", "Skip": "Pending"}
STATUS_CSS = {"Pending": "pending", "Scheduled": "sched", "Done": "done", "Skip": "skip"}


@bp.route("/targets/<int:target_id>/status", methods=["PATCH"])
def update_status(target_id):
    target = db.session.get(Target, target_id)
    if not target:
        return "Not found", 404

    telescope = request.args.get("telescope", "")
    target.status = STATUS_CYCLE.get(target.status, "Pending")

    if target.status == "Scheduled" and telescope:
        target.preferred_telescope = telescope
    elif target.status != "Scheduled":
        target.preferred_telescope = None

    db.session.commit()

    css = STATUS_CSS.get(target.status, "pending")
    return render_template(
        "partials/status_badge.html",
        target_id=target_id,
        status=target.status,
        css=css,
        telescope=telescope,
    )


@bp.route("/targets/<int:target_id>/select-telescope", methods=["PATCH"])
def select_telescope(target_id):
    """Toggle telescope selection from the compare view.

    If the target is already scheduled with this telescope, unschedule it.
    Otherwise, schedule the target with this telescope.
    """
    target = db.session.get(Target, target_id)
    if not target:
        return "Not found", 404

    telescope = request.args.get("telescope", "")
    if target.status == "Scheduled" and target.preferred_telescope == telescope:
        # Deselect: unschedule
        target.status = "Pending"
        target.preferred_telescope = None
    else:
        # Select: schedule with this telescope
        target.status = "Scheduled"
        target.preferred_telescope = telescope

    db.session.commit()

    if target.status == "Scheduled" and target.preferred_telescope == telescope:
        return render_template("partials/compare_select_badge.html",
                               target_id=target_id, telescope=telescope,
                               selected=True)
    else:
        return render_template("partials/compare_select_badge.html",
                               target_id=target_id, telescope=telescope,
                               selected=False)


@bp.route("/import/localstorage", methods=["POST"])
def import_localstorage():
    data = request.get_json()
    if not data:
        return "No JSON data", 400

    status_count = 0
    log_count = 0

    statuses = data.get("arp_st", {})
    for arp_str, status in statuses.items():
        target = db.session.query(Target).filter_by(arp_number=int(arp_str)).first()
        if target and status in ("Pending", "Scheduled", "Done", "Skip"):
            target.status = status
            status_count += 1

    logs = data.get("arp_log", [])
    for entry in logs:
        target = db.session.query(Target).filter_by(arp_number=int(entry.get("arp", 0))).first()
        if target:
            log = ImagingLog(
                target_id=target.id,
                date_imaged=entry.get("date"),
                filter_strategy=entry.get("filters"),
                exposure_minutes=entry.get("exp"),
                quality=entry.get("quality", 3),
                notes=entry.get("notes", ""),
            )
            db.session.add(log)
            log_count += 1

    db.session.commit()
    return f"<div class='card'>Imported {status_count} statuses, {log_count} log entries.</div>"
