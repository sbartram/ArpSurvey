from flask import Blueprint, render_template

bp = Blueprint("moon", __name__)


@bp.route("/moon")
def index():
    return render_template("moon.html")
