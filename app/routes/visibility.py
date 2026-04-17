from flask import Blueprint, render_template, request

from app import db
from app.models import SessionResult

bp = Blueprint("visibility", __name__)


@bp.route("/visibility")
def index():
    last = db.session.query(SessionResult).order_by(
        SessionResult.computed_at.desc()
    ).first()

    results = []
    session_info = None

    if last and last.results:
        results = last.results
        session_info = {
            "site": last.site_key,
            "date": last.date_local.isoformat() if last.date_local else "",
            "computed": last.computed_at.strftime("%Y-%m-%d %H:%M") if last.computed_at else "",
            "count": len(results),
        }

    return render_template("visibility.html", results=results, session_info=session_info)


@bp.route("/visibility/filter")
def filter_visibility():
    last = db.session.query(SessionResult).order_by(
        SessionResult.computed_at.desc()
    ).first()

    if not last or not last.results:
        return '<div class="empty-state">No session data. Run "Tonight\'s plan" first.</div>'

    results = list(last.results)

    # Apply filters
    search = request.args.get("search", "").strip().lower()
    min_hours = request.args.get("min_hours", 0, type=float)
    moon_filter = request.args.get("moon_filter", "")
    sort_by = request.args.get("sort", "transit")

    if search:
        results = [r for r in results
                   if search in str(r["arp"]) or search in r["name"].lower()]

    if min_hours > 0:
        results = [r for r in results if r["hours"] >= min_hours]

    if moon_filter == "G":
        results = [r for r in results if r["moon"]["risk"] == "G"]
    elif moon_filter == "GM":
        results = [r for r in results if r["moon"]["risk"] != "A"]

    # Sort
    if sort_by == "hours":
        results.sort(key=lambda r: r["hours"], reverse=True)
    elif sort_by == "arp":
        results.sort(key=lambda r: r["arp"])
    else:  # transit (default)
        results.sort(key=lambda r: r["transit"])

    return render_template("partials/visibility_table.html", results=results)
