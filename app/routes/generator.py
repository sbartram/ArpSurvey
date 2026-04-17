from flask import Blueprint, render_template

bp = Blueprint("generator", __name__)


@bp.route("/generator")
def index():
    return render_template("generator.html")
