import threading
from datetime import date, datetime, timezone

from flask import Blueprint, render_template, request, current_app
from arp_common import SITE_UTAH

from app import db
from app.models import Target, MoonData, MoonCalendarRun
from app.services.moon_calendar import compute_moon_data

bp = Blueprint("moon", __name__)


@bp.route("/moon")
def index():
    run = db.session.query(MoonCalendarRun).filter_by(
        status="complete"
    ).order_by(MoonCalendarRun.generated_at.desc()).first()

    targets_with_moon = []
    phase_calendar = []
    metrics = {}

    if run:
        phase_calendar = run.phase_calendar or []
        metrics = {
            "generated": run.generated_at.strftime("%Y-%m-%d"),
            "days": run.days,
            "next_new": run.next_new_moon,
            "next_full": run.next_full_moon,
        }

        # Get today's moon data for each target
        today = date.today()
        targets = db.session.query(Target).order_by(Target.arp_number).all()

        for t in targets:
            today_moon = db.session.query(MoonData).filter_by(
                target_id=t.id, night_date=today
            ).first()

            # Get all moon data for this target (for the strip)
            all_moon = db.session.query(MoonData).filter_by(
                target_id=t.id
            ).order_by(MoonData.night_date).all()

            targets_with_moon.append({
                "arp": t.arp_number,
                "name": t.name,
                "season": t.season,
                "today_risk": today_moon.risk if today_moon else "?",
                "windows": [{"d": m.night_date.isoformat(), "r": m.risk} for m in all_moon],
            })

    # Check for in-progress computation
    computing = db.session.query(MoonCalendarRun).filter_by(
        status="computing"
    ).first()

    return render_template("moon.html",
        targets_with_moon=targets_with_moon,
        phase_calendar=phase_calendar[:30],
        metrics=metrics,
        computing=computing is not None,
    )


@bp.route("/moon/regenerate", methods=["POST"])
def regenerate():
    days = request.form.get("days", 90, type=int)

    # Create a "computing" run
    run = MoonCalendarRun(
        status="computing",
        days=days,
        site_key=SITE_UTAH,
        start_date=date.today(),
        phase_calendar=[],
    )
    db.session.add(run)
    db.session.commit()
    run_id = run.id

    # Start background computation
    app = current_app._get_current_object()

    def _compute(app, run_id, days):
        with app.app_context():
            targets = db.session.query(Target).all()
            target_dicts = [{"id": t.id, "arp_number": t.arp_number,
                             "ra_hours": t.best_ra, "dec_degrees": t.best_dec}
                            for t in targets]

            rows, metadata = compute_moon_data(target_dicts, days, SITE_UTAH)

            # Clear old moon data and insert new
            db.session.query(MoonData).delete()
            db.session.add_all([MoonData(**row) for row in rows])

            # Update the run
            run = db.session.get(MoonCalendarRun, run_id)
            run.status = "complete"
            run.phase_calendar = metadata["phase_calendar"]
            run.next_new_moon = metadata["next_new_moon"]
            run.next_full_moon = metadata["next_full_moon"]
            db.session.commit()

    thread = threading.Thread(target=_compute, args=(app, run_id, days))
    thread.daemon = True
    thread.start()

    return '''<div class="card" style="text-align:center;padding:20px"
                   hx-get="/moon/status" hx-trigger="every 3s" hx-swap="outerHTML">
                <div class="card-title">Computing moon data...</div>
                <div style="color:var(--text3)">This takes about 25 seconds for 338 targets × 90 days.</div>
              </div>'''


@bp.route("/moon/status")
def status():
    computing = db.session.query(MoonCalendarRun).filter_by(
        status="computing"
    ).first()

    if computing:
        return '''<div class="card" style="text-align:center;padding:20px"
                       hx-get="/moon/status" hx-trigger="every 3s" hx-swap="outerHTML">
                    <div class="card-title">Computing moon data...</div>
                    <div style="color:var(--text3)">Still computing...</div>
                  </div>'''

    # Done — return a redirect hint to reload the page
    return '''<div hx-get="/moon" hx-trigger="load" hx-target="body" hx-swap="outerHTML"
                   hx-push-url="true">
                <div class="card" style="text-align:center;padding:20px;color:var(--accent)">
                  Done! Reloading...
                </div>
              </div>'''


@bp.route("/moon/filter")
def filter_moon():
    risk_filter = request.args.get("risk", "")
    search = request.args.get("search", "").strip().lower()

    today = date.today()
    targets = db.session.query(Target).order_by(Target.arp_number).all()

    filtered = []
    for t in targets:
        today_moon = db.session.query(MoonData).filter_by(
            target_id=t.id, night_date=today
        ).first()

        today_risk = today_moon.risk if today_moon else "?"

        if risk_filter and today_risk != risk_filter:
            continue

        if search and search not in str(t.arp_number) and search not in t.name.lower():
            continue

        all_moon = db.session.query(MoonData).filter_by(
            target_id=t.id
        ).order_by(MoonData.night_date).all()

        filtered.append({
            "arp": t.arp_number,
            "name": t.name,
            "season": t.season,
            "today_risk": today_risk,
            "windows": [{"d": m.night_date.isoformat(), "r": m.risk} for m in all_moon],
        })

    return render_template("partials/moon_strips.html", targets_with_moon=filtered)
