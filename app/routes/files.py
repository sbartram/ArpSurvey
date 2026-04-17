from flask import Blueprint, render_template

bp = Blueprint("files", __name__)


@bp.route("/files")
def index():
    return render_template("files.html")
