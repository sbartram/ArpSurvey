from flask import Blueprint, render_template

bp = Blueprint("export", __name__)


@bp.route("/export")
def index():
    return render_template("export.html")
