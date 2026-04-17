from flask import Blueprint, render_template, request, Response

from app import db
from app.models import GeneratedPlan
from app.services.importer import (
    detect_file_type, import_seasonal_plan,
    import_telescopes_file, import_ned_coords_file,
)

bp = Blueprint("files", __name__)


@bp.route("/files")
def index():
    plans = db.session.query(GeneratedPlan).order_by(
        GeneratedPlan.created_at.desc()
    ).all()
    return render_template("files.html", plans=plans)


@bp.route("/files/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file or not file.filename:
        return render_template("partials/upload_result.html",
                               success=False, message="No file selected.")

    file_type = detect_file_type(file.filename)
    if not file_type:
        return render_template("partials/upload_result.html",
                               success=False,
                               message=f"Unrecognized file: {file.filename}")

    try:
        if file_type == "seasonal_plan":
            result = import_seasonal_plan(file, db.session)
            message = (f"Imported {result['imported']} new targets, "
                       f"updated {result['updated']} existing.")
        elif file_type == "telescopes":
            result = import_telescopes_file(file, db.session)
            message = (f"Imported {result['telescopes']} telescopes, "
                       f"{result['rates']} rate entries.")
        elif file_type == "ned_coords":
            result = import_ned_coords_file(file, db.session)
            message = f"Updated NED coordinates for {result['updated']} targets."
        else:
            message = "Unknown file type."

        return render_template("partials/upload_result.html",
                               success=True, message=message)
    except Exception as e:
        db.session.rollback()
        return render_template("partials/upload_result.html",
                               success=False, message=f"Import failed: {str(e)}")


@bp.route("/files/plans/<int:plan_id>/download")
def download_plan(plan_id):
    plan = db.session.get(GeneratedPlan, plan_id)
    if not plan:
        return "Not found", 404

    return Response(
        plan.content,
        mimetype="text/plain",
        headers={"Content-Disposition": f"attachment; filename={plan.filename}"}
    )
