from flask import Blueprint, render_template

bp = Blueprint("log", __name__)


@bp.route("/log")
def index():
    return render_template("log.html")
