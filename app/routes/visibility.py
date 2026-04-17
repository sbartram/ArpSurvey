from flask import Blueprint, render_template

bp = Blueprint("visibility", __name__)


@bp.route("/visibility")
def index():
    return render_template("visibility.html")
