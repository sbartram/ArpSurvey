from flask import Blueprint, render_template

bp = Blueprint("planner", __name__)


@bp.route("/planner")
def index():
    return render_template("planner.html")
