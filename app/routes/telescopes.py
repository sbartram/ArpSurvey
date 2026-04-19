import re

from flask import Blueprint, render_template
from sqlalchemy import func

from app import db
from app.models import Telescope

bp = Blueprint("telescopes", __name__)


def _natural_sort_key(tel):
    """Sort T5 before T14 by extracting the numeric part."""
    m = re.match(r"([A-Za-z]+)(\d+)", tel.telescope_id)
    if m:
        return (m.group(1), int(m.group(2)))
    return (tel.telescope_id, 0)


@bp.route("/telescopes")
def index():
    telescopes = Telescope.query.all()
    telescopes.sort(key=_natural_sort_key)
    online = sum(1 for t in telescopes if t.active)
    total = len(telescopes)
    return render_template(
        "telescopes.html",
        telescopes=telescopes,
        total=total,
        online=online,
        offline=total - online,
    )


@bp.route("/telescopes/<int:telescope_id>/toggle", methods=["PATCH"])
def toggle_active(telescope_id):
    telescope = db.session.get(Telescope, telescope_id)
    if not telescope:
        return "Not found", 404
    telescope.active = not telescope.active
    db.session.commit()

    total = db.session.query(func.count(Telescope.id)).scalar()
    online = db.session.query(func.count(Telescope.id)).filter(Telescope.active.is_(True)).scalar()

    row_html = render_template("partials/telescope_row.html", telescope=telescope)
    metrics_html = render_template("partials/telescope_metrics.html",
                                   total=total, online=online, offline=total - online,
                                   oob=True)
    return row_html + metrics_html
