# Telescope Match Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Compare Telescopes" feature to the session planner that ranks all telescopes for a specific Arp target on a given date, with composite quality scoring and per-metric sorting.

**Architecture:** A new pure-computation service (`telescope_match.py`) evaluates each telescope against a target+date, computing visibility, SNR, FOV fit, and cost metrics. A new route (`GET /planner/compare`) serves an HTMX partial that swaps into the planner results area, showing viable telescopes ranked by composite score and excluded telescopes greyed out with reasons.

**Tech Stack:** Python, Flask, SQLAlchemy, ephem, HTMX, Jinja2

**Spec:** `docs/superpowers/specs/2026-04-18-telescope-match-design.md`

---

### Task 1: Core Evaluation — `evaluate_telescope()`

**Files:**
- Create: `app/services/telescope_match.py`
- Create: `tests/test_telescope_match.py`

This task builds the function that computes all metrics for a single telescope+target+date combination, including disqualification checks.

- [ ] **Step 1: Write the failing test for a viable telescope evaluation**

In `tests/test_telescope_match.py`:

```python
"""Tests for the telescope match service."""

import datetime
import math
import pytest

from app import create_app, db
from app.config import Config
from app.models import Telescope, TelescopeRate


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


def _make_telescope(tel_id="T14", site="New Mexico", fov=60.0, resolution=1.1,
                    filters=None, aperture=250, read_noise=8.0, dark_current=0.05,
                    peak_qe=0.6, full_well=25000, pixel_size=9.0, focal_length=2000):
    """Helper to build a Telescope instance for testing."""
    return Telescope(
        telescope_id=tel_id, site=site, fov_arcmin=fov, resolution=resolution,
        filters=filters or ["L", "R", "G", "B", "Ha"],
        aperture_mm=aperture, focal_length_mm=focal_length,
        pixel_size_um=pixel_size, peak_qe=peak_qe, full_well_e=full_well,
        read_noise_e=read_noise, dark_current_e=dark_current,
        camera_model="Test CCD", sensor_model="Test Sensor", sensor_type="CCD",
    )


def _make_rate(telescope, plan_tier="Plan-40", session_rate=12.0, exposure_rate=8.0):
    """Helper to build a TelescopeRate instance for testing."""
    return TelescopeRate(
        telescope=telescope, plan_tier=plan_tier,
        session_rate=session_rate, exposure_rate=exposure_rate,
    )


# M51 (Arp 85): bright, large, high-Dec — observable from New Mexico in April
SAMPLE_TARGET = {
    "arp_number": 85,
    "name": "M51",
    "ra_hours": 13.5,
    "dec_degrees": 47.2,
    "size_arcmin": 11.0,
    "magnitude": 8.4,
    "filter_strategy": "LRGB",
}

SAMPLE_DATE = datetime.date(2026, 4, 17)


def test_evaluate_telescope_viable(app):
    from app.services.telescope_match import evaluate_telescope

    with app.app_context():
        tel = _make_telescope()
        rate = _make_rate(tel)
        db.session.add(tel)
        db.session.add(rate)
        db.session.commit()

        result = evaluate_telescope(
            target=SAMPLE_TARGET,
            telescope=tel,
            date=SAMPLE_DATE,
            site_key="New Mexico",
            moon_info={"phase_pct": 20.0, "separation_deg": 90.0, "risk": "G"},
        )

    assert result["disqualified"] is False
    assert result["disqualification_reason"] is None
    assert result["peak_elevation"] > 30
    assert result["hours"] > 0
    assert result["airmass"] > 1.0
    assert result["target_pixels"] > 0
    assert result["fov_fill_pct"] > 0
    assert result["snr_single"] > 0
    assert result["time_to_snr_minutes"] > 0
    assert result["cost_points"] > 0
    assert result["moon_risk"] == "G"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_telescope_match.py::test_evaluate_telescope_viable -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.telescope_match'`

- [ ] **Step 3: Write the `evaluate_telescope()` implementation**

In `app/services/telescope_match.py`:

```python
"""
Telescope match service.

Evaluates and ranks telescopes for a specific target on a given date.
Computes visibility, SNR, FOV fit, cost, and a composite quality score.
"""

import math
import datetime

from arp_common import OBSERVATORIES

from app.services.astronomy import dark_window, target_visibility, alt_at_time
from app.services.snr import estimate_snr


DEFAULT_SNR_TARGET = 30
DEFAULT_PLAN_TIER = "Plan-40"
DEFAULT_MIN_ELEVATION = 30
DEFAULT_EXPOSURE_SECS = 300

SCORE_WEIGHTS = {
    "time_to_snr": 0.35,
    "fov_fit": 0.20,
    "hours": 0.20,
    "elevation": 0.15,
    "cost": 0.10,
}


def evaluate_telescope(target, telescope, date, site_key, moon_info,
                       snr_target=DEFAULT_SNR_TARGET, plan_tier=DEFAULT_PLAN_TIER):
    """
    Compute all comparison metrics for one target+telescope+date.

    Args:
        target: dict with keys arp_number, name, ra_hours, dec_degrees,
                size_arcmin, magnitude, filter_strategy
        telescope: Telescope model instance
        date: observation date (datetime.date)
        site_key: observatory name matching telescope.site
        moon_info: dict with phase_pct, separation_deg, risk
        snr_target: desired SNR goal (default 30)
        plan_tier: billing plan tier (default "Plan-40")

    Returns dict with all metrics plus disqualified/disqualification_reason.
    """
    ra_h = target["ra_hours"]
    dec_deg = target["dec_degrees"]
    size = target.get("size_arcmin") or 1.0
    mag = target.get("magnitude")
    strategy = target.get("filter_strategy", "Luminance")

    base = {
        "telescope_id": telescope.telescope_id,
        "site": telescope.site,
        "aperture_mm": telescope.aperture_mm,
    }

    # --- Disqualification: target visibility ---
    eve_dt, morn_dt = dark_window(site_key, date)
    vis = target_visibility(ra_h, dec_deg, site_key, eve_dt, morn_dt)

    if not vis or vis["hours"] <= 0:
        return {**base, "disqualified": True,
                "disqualification_reason": f"Target never above {DEFAULT_MIN_ELEVATION}\u00b0 during dark window"}

    peak_el = round(alt_at_time(ra_h, dec_deg, site_key, vis["transit"]), 1)
    hours = vis["hours"]
    airmass = round(1.0 / math.sin(math.radians(max(peak_el, 10))), 2)

    # --- Disqualification: FOV ---
    fov = telescope.fov_arcmin or 60.0
    fov_fill_pct = round(size / fov * 100, 1)

    if fov_fill_pct > 100:
        return {**base, "disqualified": True,
                "disqualification_reason": f"Target ({size:.1f}') exceeds telescope FOV ({fov:.0f}')"}

    # --- Disqualification: filters ---
    tel_filters = set(telescope.filters or [])
    required = _required_filters(strategy)
    missing = required - tel_filters
    if missing:
        return {**base, "disqualified": True,
                "disqualification_reason": f"Missing filter(s): {', '.join(sorted(missing))}"}

    # --- Disqualification: no magnitude ---
    if mag is None:
        return {**base, "disqualified": True,
                "disqualification_reason": "No magnitude data for SNR calculation"}

    # --- Metrics ---
    resolution = telescope.resolution or 1.0
    target_pixels = round(size * 60 / resolution)

    snr_result = estimate_snr(
        target_mag=mag,
        target_size_arcmin=size,
        telescope=telescope,
        site_key=site_key,
        elevation_deg=peak_el,
        moon_phase_pct=moon_info["phase_pct"],
        moon_sep_deg=moon_info["separation_deg"],
    )

    if not snr_result or snr_result["snr_single"] <= 0:
        return {**base, "disqualified": True,
                "disqualification_reason": "Could not compute SNR (insufficient telescope specs)"}

    snr_single = snr_result["snr_single"]
    n_subs = math.ceil((snr_target / snr_single) ** 2) if snr_single < snr_target else 1
    time_to_snr_secs = n_subs * DEFAULT_EXPOSURE_SECS
    time_to_snr_minutes = round(time_to_snr_secs / 60, 1)

    # Cost from exposure rate
    rate = telescope.rates.filter_by(plan_tier=plan_tier).first()
    exposure_rate = rate.exposure_rate if rate else 0
    cost_points = round(time_to_snr_minutes * exposure_rate, 1)

    return {
        **base,
        "disqualified": False,
        "disqualification_reason": None,
        "peak_elevation": peak_el,
        "hours": hours,
        "airmass": airmass,
        "target_pixels": target_pixels,
        "fov_fill_pct": fov_fill_pct,
        "snr_single": snr_single,
        "n_subs": n_subs,
        "time_to_snr_minutes": time_to_snr_minutes,
        "cost_points": cost_points,
        "moon_risk": moon_info["risk"],
        "effective_sky_mag": snr_result["effective_sky_mag"],
    }


def _required_filters(strategy):
    """Return the set of filter letters required for a given strategy."""
    s = strategy.upper() if strategy else "L"
    if "LRGB" in s:
        return {"L", "R", "G", "B"}
    if "HA" in s or "NARROWBAND" in s:
        return {"Ha"}
    return {"L"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_telescope_match.py::test_evaluate_telescope_viable -v`
Expected: PASS

- [ ] **Step 5: Write failing tests for disqualification cases**

Append to `tests/test_telescope_match.py`:

```python
def test_evaluate_telescope_below_horizon(app):
    """A southern-sky target should be disqualified from an Australian telescope in April
    if it never rises high enough — use a high-Dec northern target from Australia."""
    from app.services.telescope_match import evaluate_telescope

    northern_target = {
        "arp_number": 85, "name": "M51", "ra_hours": 13.5, "dec_degrees": 47.2,
        "size_arcmin": 11.0, "magnitude": 8.4, "filter_strategy": "LRGB",
    }

    with app.app_context():
        tel = _make_telescope(tel_id="T24", site="Australia")
        db.session.add(tel)
        db.session.commit()

        result = evaluate_telescope(
            target=northern_target, telescope=tel, date=SAMPLE_DATE,
            site_key="Australia",
            moon_info={"phase_pct": 20.0, "separation_deg": 90.0, "risk": "G"},
        )

    assert result["disqualified"] is True
    assert "above" in result["disqualification_reason"].lower() or \
           "elevation" in result["disqualification_reason"].lower()


def test_evaluate_telescope_fov_clipped(app):
    from app.services.telescope_match import evaluate_telescope

    large_target = {**SAMPLE_TARGET, "size_arcmin": 80.0}

    with app.app_context():
        tel = _make_telescope(fov=60.0)  # target bigger than FOV
        db.session.add(tel)
        db.session.commit()

        result = evaluate_telescope(
            target=large_target, telescope=tel, date=SAMPLE_DATE,
            site_key="New Mexico",
            moon_info={"phase_pct": 20.0, "separation_deg": 90.0, "risk": "G"},
        )

    assert result["disqualified"] is True
    assert "FOV" in result["disqualification_reason"]


def test_evaluate_telescope_missing_filters(app):
    from app.services.telescope_match import evaluate_telescope

    with app.app_context():
        tel = _make_telescope(filters=["L"])  # LRGB target, Lum-only scope
        db.session.add(tel)
        db.session.commit()

        result = evaluate_telescope(
            target=SAMPLE_TARGET, telescope=tel, date=SAMPLE_DATE,
            site_key="New Mexico",
            moon_info={"phase_pct": 20.0, "separation_deg": 90.0, "risk": "G"},
        )

    assert result["disqualified"] is True
    assert "filter" in result["disqualification_reason"].lower()
```

- [ ] **Step 6: Run disqualification tests to verify they pass**

Run: `.venv/bin/pytest tests/test_telescope_match.py -k "disqualif or below_horizon or fov_clipped or missing_filters" -v`
Expected: 3 PASSED

- [ ] **Step 7: Write failing tests for metric calculations**

Append to `tests/test_telescope_match.py`:

```python
def test_time_to_snr_calculation(app):
    """Verify n_subs = ceil((target / single)^2)."""
    from app.services.telescope_match import evaluate_telescope

    with app.app_context():
        tel = _make_telescope()
        rate = _make_rate(tel)
        db.session.add(tel)
        db.session.add(rate)
        db.session.commit()

        result = evaluate_telescope(
            target=SAMPLE_TARGET, telescope=tel, date=SAMPLE_DATE,
            site_key="New Mexico",
            moon_info={"phase_pct": 20.0, "separation_deg": 90.0, "risk": "G"},
            snr_target=30,
        )

    snr_s = result["snr_single"]
    expected_n = math.ceil((30 / snr_s) ** 2) if snr_s < 30 else 1
    assert result["n_subs"] == expected_n
    assert result["time_to_snr_minutes"] == round(expected_n * 300 / 60, 1)


def test_fov_fill_ratio(app):
    from app.services.telescope_match import evaluate_telescope

    target = {**SAMPLE_TARGET, "size_arcmin": 6.0}

    with app.app_context():
        tel = _make_telescope(fov=60.0, resolution=1.0)
        rate = _make_rate(tel)
        db.session.add(tel)
        db.session.add(rate)
        db.session.commit()

        result = evaluate_telescope(
            target=target, telescope=tel, date=SAMPLE_DATE,
            site_key="New Mexico",
            moon_info={"phase_pct": 20.0, "separation_deg": 90.0, "risk": "G"},
        )

    assert result["fov_fill_pct"] == 10.0  # 6.0 / 60.0 * 100
    assert result["target_pixels"] == 360   # 6.0 * 60 / 1.0
```

- [ ] **Step 8: Run metric tests to verify they pass**

Run: `.venv/bin/pytest tests/test_telescope_match.py -k "time_to_snr or fov_fill" -v`
Expected: 2 PASSED

- [ ] **Step 9: Commit**

```bash
git add app/services/telescope_match.py tests/test_telescope_match.py
git commit -m "feat: add evaluate_telescope() for telescope match scoring"
```

---

### Task 2: Comparison & Composite Scoring — `compare_telescopes()`

**Files:**
- Modify: `app/services/telescope_match.py`
- Modify: `tests/test_telescope_match.py`

This task adds the function that evaluates all telescopes and computes composite quality scores with min-max normalization.

- [ ] **Step 1: Write failing tests for `compare_telescopes()`**

Append to `tests/test_telescope_match.py`:

```python
def test_compare_telescopes_splits_viable_and_excluded(app):
    from app.services.telescope_match import compare_telescopes

    with app.app_context():
        # Viable telescope: full LRGB filters, NM site
        tel1 = _make_telescope(tel_id="T14", site="New Mexico", filters=["L", "R", "G", "B"])
        rate1 = _make_rate(tel1)
        # Excluded telescope: Lum-only (missing RGB for LRGB target)
        tel2 = _make_telescope(tel_id="T99", site="New Mexico", filters=["L"],
                               aperture=100, fov=30.0)
        db.session.add_all([tel1, rate1, tel2])
        db.session.commit()

        result = compare_telescopes(
            target=SAMPLE_TARGET,
            date=SAMPLE_DATE,
            moon_info={"phase_pct": 20.0, "separation_deg": 90.0, "risk": "G"},
        )

    assert len(result["viable"]) >= 1
    assert len(result["excluded"]) >= 1
    # Viable telescopes have a score
    for v in result["viable"]:
        assert "score" in v
        assert 0 <= v["score"] <= 100
    # Excluded telescopes have no score
    for e in result["excluded"]:
        assert "score" not in e or e.get("score") is None


def test_composite_score_normalization(app):
    from app.services.telescope_match import compare_telescopes

    with app.app_context():
        tel1 = _make_telescope(tel_id="T14", aperture=250, fov=60.0,
                               filters=["L", "R", "G", "B"])
        rate1 = _make_rate(tel1)
        tel2 = _make_telescope(tel_id="T21", aperture=430, fov=40.0, resolution=0.6,
                               filters=["L", "R", "G", "B"])
        rate2 = _make_rate(tel2)
        db.session.add_all([tel1, rate1, tel2, rate2])
        db.session.commit()

        result = compare_telescopes(
            target=SAMPLE_TARGET,
            date=SAMPLE_DATE,
            moon_info={"phase_pct": 20.0, "separation_deg": 90.0, "risk": "G"},
        )

    for v in result["viable"]:
        assert 0 <= v["score"] <= 100


def test_compare_telescopes_custom_snr_target(app):
    from app.services.telescope_match import compare_telescopes

    with app.app_context():
        tel = _make_telescope(filters=["L", "R", "G", "B"])
        rate = _make_rate(tel)
        db.session.add_all([tel, rate])
        db.session.commit()

        result_30 = compare_telescopes(
            target=SAMPLE_TARGET, date=SAMPLE_DATE,
            moon_info={"phase_pct": 20.0, "separation_deg": 90.0, "risk": "G"},
            snr_target=30,
        )
        result_60 = compare_telescopes(
            target=SAMPLE_TARGET, date=SAMPLE_DATE,
            moon_info={"phase_pct": 20.0, "separation_deg": 90.0, "risk": "G"},
            snr_target=60,
        )

    v30 = result_30["viable"][0]
    v60 = result_60["viable"][0]
    # Higher SNR target = more time and cost
    assert v60["time_to_snr_minutes"] >= v30["time_to_snr_minutes"]
    assert v60["cost_points"] >= v30["cost_points"]
    # Elevation and hours should be the same (same night, same telescope)
    assert v30["peak_elevation"] == v60["peak_elevation"]
    assert v30["hours"] == v60["hours"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_telescope_match.py -k "compare" -v`
Expected: FAIL — `ImportError: cannot import name 'compare_telescopes'`

- [ ] **Step 3: Implement `compare_telescopes()` and `_compute_scores()`**

Append to `app/services/telescope_match.py`:

```python
def compare_telescopes(target, date, moon_info, snr_target=DEFAULT_SNR_TARGET,
                       plan_tier=DEFAULT_PLAN_TIER):
    """
    Evaluate all telescopes in the DB for a target+date.

    Args:
        target: dict with arp_number, name, ra_hours, dec_degrees,
                size_arcmin, magnitude, filter_strategy
        date: observation date (datetime.date)
        moon_info: dict with phase_pct, separation_deg, risk
        snr_target: desired SNR goal
        plan_tier: billing tier for cost calculation

    Returns dict: {"viable": [...], "excluded": [...]}
        viable: sorted by composite score descending
        excluded: sorted by telescope_id
    """
    from app.models import Telescope

    telescopes = Telescope.query.all()

    viable = []
    excluded = []

    for tel in telescopes:
        result = evaluate_telescope(
            target=target, telescope=tel, date=date,
            site_key=tel.site, moon_info=moon_info,
            snr_target=snr_target, plan_tier=plan_tier,
        )
        if result["disqualified"]:
            excluded.append(result)
        else:
            viable.append(result)

    _compute_scores(viable)

    viable.sort(key=lambda r: r.get("score", 0), reverse=True)
    excluded.sort(key=lambda r: r.get("telescope_id", ""))

    return {"viable": viable, "excluded": excluded}


def _compute_scores(viable):
    """Compute composite quality scores using min-max normalization."""
    if not viable:
        return

    if len(viable) == 1:
        viable[0]["score"] = 75  # single option gets a decent score
        return

    # Extract raw values
    times = [r["time_to_snr_minutes"] for r in viable]
    fills = [r["fov_fill_pct"] for r in viable]
    hours = [r["hours"] for r in viable]
    elevs = [r["peak_elevation"] for r in viable]
    costs = [r["cost_points"] for r in viable]

    for r in viable:
        # Time to SNR: lower is better → invert
        t_norm = 1.0 - _min_max_norm(r["time_to_snr_minutes"], times)

        # FOV fill: optimal 10-60%, penalize outside
        f_norm = _fov_fit_score(r["fov_fill_pct"])

        # Hours: higher is better
        h_norm = _min_max_norm(r["hours"], hours)

        # Elevation: higher is better
        e_norm = _min_max_norm(r["peak_elevation"], elevs)

        # Cost: lower is better → invert
        c_norm = 1.0 - _min_max_norm(r["cost_points"], costs)

        raw = (SCORE_WEIGHTS["time_to_snr"] * t_norm +
               SCORE_WEIGHTS["fov_fit"] * f_norm +
               SCORE_WEIGHTS["hours"] * h_norm +
               SCORE_WEIGHTS["elevation"] * e_norm +
               SCORE_WEIGHTS["cost"] * c_norm)

        r["score"] = round(raw * 100, 1)


def _min_max_norm(value, values):
    """Normalize value to 0-1 range within values. Returns 0.5 if all equal."""
    lo, hi = min(values), max(values)
    if hi == lo:
        return 0.5
    return (value - lo) / (hi - lo)


def _fov_fit_score(fill_pct):
    """Score FOV fill percentage. Optimal range 10-60%, penalized outside."""
    if fill_pct <= 0:
        return 0.0
    if fill_pct <= 10:
        return fill_pct / 10.0 * 0.7   # ramp up to 0.7 at 10%
    if fill_pct <= 60:
        return 0.7 + (fill_pct - 10) / 50.0 * 0.3  # 0.7 to 1.0
    if fill_pct <= 100:
        return 1.0 - (fill_pct - 60) / 40.0 * 0.8  # 1.0 down to 0.2
    return 0.0  # clipped
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_telescope_match.py -v`
Expected: ALL PASSED (8 tests)

- [ ] **Step 5: Commit**

```bash
git add app/services/telescope_match.py tests/test_telescope_match.py
git commit -m "feat: add compare_telescopes() with composite scoring"
```

---

### Task 3: Planner Route — `GET /planner/compare`

**Files:**
- Modify: `app/routes/planner.py`
- Modify: `tests/test_telescope_match.py`

This task adds the route that handles the comparison request and prepares data for the template.

- [ ] **Step 1: Write failing test for the compare route**

Append to `tests/test_telescope_match.py`:

```python
@pytest.fixture
def client(app):
    return app.test_client()


def test_compare_route_returns_200(app, client):
    from app.models import Target

    with app.app_context():
        # Seed a target and telescope
        target = Target(
            arp_number=85, name="M51", ra_hours=13.5, dec_degrees=47.2,
            size_arcmin=11.0, magnitude=8.4, season="Spring",
            filter_strategy="LRGB", best_site="New Mexico / Spain",
        )
        tel = _make_telescope(filters=["L", "R", "G", "B"])
        rate = _make_rate(tel)
        db.session.add_all([target, tel, rate])
        db.session.commit()

        response = client.get("/planner/compare?arp=85&date=2026-04-17&site=New+Mexico")

    assert response.status_code == 200
    html = response.data.decode()
    assert "M51" in html
    assert "T14" in html


def test_compare_route_missing_arp_returns_error(app, client):
    response = client.get("/planner/compare?date=2026-04-17&site=New+Mexico")
    assert response.status_code == 200
    html = response.data.decode()
    assert "not found" in html.lower() or "no target" in html.lower()


def test_restore_route_returns_planner_table(app, client):
    from app.models import Target, SessionResult

    with app.app_context():
        target = Target(
            arp_number=85, name="M51", ra_hours=13.5, dec_degrees=47.2,
            size_arcmin=11.0, magnitude=8.4, season="Spring",
            filter_strategy="LRGB", best_site="New Mexico / Spain",
        )
        db.session.add(target)
        db.session.flush()

        # Seed a session result
        import datetime as dt
        session = SessionResult(
            site_key="New Mexico",
            date_local=dt.date(2026, 4, 17),
            eve_twilight=dt.datetime(2026, 4, 18, 2, 30),
            morn_twilight=dt.datetime(2026, 4, 18, 11, 0),
            results=[{
                "arp": 85, "name": "M51", "telescope": "T14",
                "filter_strategy": "LRGB", "moon": {"risk": "G"},
                "transit": "2026-04-18T06:00:00",
            }],
        )
        db.session.add(session)
        db.session.commit()

        response = client.get("/planner/restore")

    assert response.status_code == 200
    html = response.data.decode()
    assert "M51" in html or "T14" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_telescope_match.py::test_compare_route_returns_200 -v`
Expected: FAIL — 404 (route doesn't exist yet)

- [ ] **Step 3: Add the compare route to `app/routes/planner.py`**

Add this import at the top of `app/routes/planner.py` (after existing imports):

```python
from app.services.telescope_match import compare_telescopes, DEFAULT_SNR_TARGET
from app.services.astronomy import build_observer, moon_info as compute_moon_info
```

Add this route function at the end of the file (before `generate_acp`):

```python
@bp.route("/planner/compare")
def compare():
    arp_str = request.args.get("arp")
    date_str = request.args.get("date") or datetime.date.today().isoformat()
    site_key = request.args.get("site", "New Mexico")
    snr_target = request.args.get("snr_target", DEFAULT_SNR_TARGET, type=float)
    sort_by = request.args.get("sort", "score")
    sort_dir = request.args.get("dir", "desc")

    if not arp_str:
        return '<div class="empty-state">No target specified.</div>'

    target_record = db.session.query(Target).filter_by(
        arp_number=int(arp_str)
    ).first()
    if not target_record:
        return f'<div class="empty-state">Target Arp {arp_str} not found.</div>'

    obs_date = datetime.date.fromisoformat(date_str)

    target = {
        "arp_number": target_record.arp_number,
        "name": target_record.name,
        "ra_hours": target_record.best_ra,
        "dec_degrees": target_record.best_dec,
        "size_arcmin": target_record.size_arcmin,
        "magnitude": target_record.magnitude,
        "filter_strategy": target_record.filter_strategy,
    }

    # Compute moon info for this target on this date
    obs = build_observer(site_key, obs_date)
    mi = compute_moon_info(target["ra_hours"], target["dec_degrees"], obs)

    result = compare_telescopes(
        target=target, date=obs_date, moon_info=mi,
        snr_target=snr_target,
    )

    # Apply column sort to viable list
    if sort_by != "score":
        reverse = sort_dir == "desc"
        sort_keys = {
            "telescope": lambda r: r.get("telescope_id", ""),
            "site": lambda r: r.get("site", ""),
            "elevation": lambda r: r.get("peak_elevation", 0),
            "hours": lambda r: r.get("hours", 0),
            "airmass": lambda r: r.get("airmass", 99),
            "pixels": lambda r: r.get("target_pixels", 0),
            "fov": lambda r: r.get("fov_fill_pct", 0),
            "snr": lambda r: r.get("snr_single", 0),
            "time": lambda r: r.get("time_to_snr_minutes", 9999),
            "cost": lambda r: r.get("cost_points", 9999),
            "moon": lambda r: {"G": 0, "M": 1, "A": 2}.get(r.get("moon_risk", ""), 3),
        }
        key_fn = sort_keys.get(sort_by, lambda r: r.get("score", 0))
        result["viable"].sort(key=key_fn, reverse=reverse)

    return render_template("partials/telescope_compare.html",
                           target=target, date=date_str, site=site_key,
                           snr_target=snr_target,
                           viable=result["viable"],
                           excluded=result["excluded"])


@bp.route("/planner/restore")
def restore():
    """Re-render the full planner table from the last SessionResult.

    Used by the compare view's "Back to targets" button, since the compare
    swap destroys #planner-filters and the filter route can't restore the
    full table layout.
    """
    last = db.session.query(SessionResult).order_by(
        SessionResult.computed_at.desc()
    ).first()
    if not last or not last.results:
        return '<div class="empty-state">No session data. Compute a session first.</div>'

    results = list(last.results)
    utc_offset = OBSERVATORIES[last.site_key]["utc_offset"]
    eve_local = (last.eve_twilight + datetime.timedelta(hours=utc_offset)).strftime("%H:%M")
    morn_local = (last.morn_twilight + datetime.timedelta(hours=utc_offset)).strftime("%H:%M")
    dark_hrs = round((last.morn_twilight - last.eve_twilight).total_seconds() / 3600, 1)

    telescopes = sorted(set(r["telescope"] for r in results))
    strategies = sorted(set(r["filter_strategy"] for r in results))

    summary = {
        "date": last.date_local.isoformat(), "site": last.site_key,
        "eve_local": eve_local, "morn_local": morn_local,
        "dark_hrs": dark_hrs, "total": len(results),
        "good": sum(1 for r in results if r["moon"]["risk"] == "G"),
        "marginal": sum(1 for r in results if r["moon"]["risk"] == "M"),
        "avoid": sum(1 for r in results if r["moon"]["risk"] == "A"),
    }

    return render_template("partials/planner_table.html",
                           results=results, summary=summary,
                           telescopes=telescopes, strategies=strategies)
```

- [ ] **Step 4: Create a minimal template placeholder**

Create `app/templates/partials/telescope_compare.html`:

```html
<div class="card" style="margin-bottom:12px">
  <a href="#" style="text-decoration:none"
     hx-get="/planner/restore" hx-target="#planner-results" hx-swap="innerHTML"
     >&larr; Back to targets</a>
  &nbsp;&middot;&nbsp;
  <strong>Arp {{ target.arp_number }} &mdash; {{ target.name }}</strong>
  &nbsp;&middot;&nbsp;
  V mag: {{ target.magnitude or '?' }} | Size: {{ target.size_arcmin or '?' }}'
</div>

<div class="empty-state">Template placeholder &mdash; full UI in Task 4.</div>
```

- [ ] **Step 5: Run route tests to verify they pass**

Run: `.venv/bin/pytest tests/test_telescope_match.py -k "route or restore" -v`
Expected: 3 PASSED

- [ ] **Step 6: Run full test suite to verify nothing is broken**

Run: `.venv/bin/pytest tests/ -v`
Expected: ALL PASSED

- [ ] **Step 7: Commit**

```bash
git add app/routes/planner.py app/templates/partials/telescope_compare.html tests/test_telescope_match.py
git commit -m "feat: add GET /planner/compare route for telescope matching"
```

---

### Task 4: Comparison Template & Planner Integration

**Files:**
- Modify: `app/templates/partials/telescope_compare.html`
- Modify: `app/templates/partials/planner_rows.html`
- Modify: `app/templates/partials/planner_table.html`

This task builds the full comparison UI and adds the "Compare" button to planner rows.

- [ ] **Step 1: Build the full comparison template**

Replace the content of `app/templates/partials/telescope_compare.html`:

```html
<div class="card" style="font-size:13px;color:var(--text2);margin-bottom:12px">
  <a href="#" style="text-decoration:none"
     hx-get="/planner/restore" hx-target="#planner-results" hx-swap="innerHTML"
     >&larr; Back to targets</a>
  &nbsp;&middot;&nbsp;
  <strong>Arp {{ target.arp_number }} &mdash; {{ target.name }}</strong>
  &nbsp;&middot;&nbsp;
  V mag: {{ target.magnitude or '?' }} | Size: {{ target.size_arcmin or '?' }}'
  &nbsp;&middot;&nbsp;
  <label style="font-size:12px">
    SNR target:
    <input type="number" name="snr_target" value="{{ snr_target }}" min="1" max="999"
           style="width:60px"
           hx-get="/planner/compare?arp={{ target.arp_number }}&date={{ date }}&site={{ site }}"
           hx-target="#planner-results" hx-swap="innerHTML"
           hx-trigger="change" hx-include="this">
  </label>
</div>

{% if viable %}
<div class="tbl-wrap">
  <table>
    <thead>
      <tr>
        {% set base = "/planner/compare?arp=" ~ target.arp_number ~ "&date=" ~ date ~ "&site=" ~ site ~ "&snr_target=" ~ snr_target %}
        <th style="cursor:pointer" hx-get="{{ base }}&sort=score&dir=desc" hx-target="#planner-results" hx-swap="innerHTML">Score</th>
        <th style="cursor:pointer" hx-get="{{ base }}&sort=telescope&dir=asc" hx-target="#planner-results" hx-swap="innerHTML">Telescope</th>
        <th style="cursor:pointer" hx-get="{{ base }}&sort=site&dir=asc" hx-target="#planner-results" hx-swap="innerHTML">Site</th>
        <th style="cursor:pointer" hx-get="{{ base }}&sort=elevation&dir=desc" hx-target="#planner-results" hx-swap="innerHTML">Peak El</th>
        <th style="cursor:pointer" hx-get="{{ base }}&sort=hours&dir=desc" hx-target="#planner-results" hx-swap="innerHTML">Hrs</th>
        <th style="cursor:pointer" hx-get="{{ base }}&sort=airmass&dir=asc" hx-target="#planner-results" hx-swap="innerHTML">Airmass</th>
        <th style="cursor:pointer" hx-get="{{ base }}&sort=pixels&dir=desc" hx-target="#planner-results" hx-swap="innerHTML">Pixels</th>
        <th style="cursor:pointer" hx-get="{{ base }}&sort=fov&dir=asc" hx-target="#planner-results" hx-swap="innerHTML">FOV%</th>
        <th style="cursor:pointer" hx-get="{{ base }}&sort=snr&dir=desc" hx-target="#planner-results" hx-swap="innerHTML">SNR/sub</th>
        <th style="cursor:pointer" hx-get="{{ base }}&sort=time&dir=asc" hx-target="#planner-results" hx-swap="innerHTML">Time</th>
        <th style="cursor:pointer" hx-get="{{ base }}&sort=cost&dir=asc" hx-target="#planner-results" hx-swap="innerHTML">Cost</th>
        <th style="cursor:pointer" hx-get="{{ base }}&sort=moon&dir=asc" hx-target="#planner-results" hx-swap="innerHTML">Moon</th>
      </tr>
    </thead>
    <tbody>
      {% for r in viable %}
      <tr>
        <td>
          {% if r.score >= 70 %}
            <span class="badge G" title="Score: {{ r.score }}">{{ r.score|round|int }}</span>
          {% elif r.score >= 40 %}
            <span class="badge M" title="Score: {{ r.score }}">{{ r.score|round|int }}</span>
          {% else %}
            <span class="badge A" title="Score: {{ r.score }}">{{ r.score|round|int }}</span>
          {% endif %}
        </td>
        <td>{{ r.telescope_id }}</td>
        <td>{{ r.site }}</td>
        <td>{{ r.peak_elevation }}&deg;</td>
        <td>{{ r.hours }}</td>
        <td>{{ r.airmass }}</td>
        <td>{{ r.target_pixels }}</td>
        <td>{{ r.fov_fill_pct }}%</td>
        <td>{{ r.snr_single }}</td>
        <td>{{ r.time_to_snr_minutes }}m</td>
        <td>{{ r.cost_points }} pts</td>
        <td><span class="badge {{ r.moon_risk }}">{{ r.moon_risk }}</span></td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% else %}
<div class="empty-state">No viable telescopes found for this target.</div>
{% endif %}

{% if excluded %}
<details style="margin-top:16px">
  <summary style="cursor:pointer;font-size:13px;color:var(--text3)">
    {{ excluded|length }} excluded telescope{{ 's' if excluded|length != 1 }}
  </summary>
  <div class="tbl-wrap" style="opacity:0.5;margin-top:8px">
    <table>
      <thead>
        <tr>
          <th>Telescope</th>
          <th>Site</th>
          <th>Reason</th>
        </tr>
      </thead>
      <tbody>
        {% for r in excluded %}
        <tr>
          <td>{{ r.telescope_id }}</td>
          <td>{{ r.site }}</td>
          <td>{{ r.disqualification_reason }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</details>
{% endif %}
```

- [ ] **Step 2: Add the "Compare" button to planner rows**

In `app/templates/partials/planner_rows.html`, add a new `<td>` after the status badge column (after line 26, before `</tr>`):

```html
  <td>
    <button class="btn-sm"
            hx-get="/planner/compare?arp={{ r.arp }}&date={{ date }}&site={{ site }}"
            hx-target="#planner-results" hx-swap="innerHTML"
            style="font-size:11px;padding:2px 8px;cursor:pointer">Compare</button>
  </td>
```

- [ ] **Step 3: Add the "Compare" column header to the planner table**

In `app/templates/partials/planner_table.html`, add a new `<th>` after the Status header (after the `</th>` on the Status column, before `</tr>`):

```html
        <th></th>
```

Also update the colspan in the empty-state row. In `planner_rows.html`, change:

```html
<tr><td colspan="14" class="empty-state">No targets match the current filters.</td></tr>
```

- [ ] **Step 4: Pass `date` and `site` to the rows template**

In `app/routes/planner.py`, the `compute()` function already passes these values to the `planner_table.html` template. Verify they're available in `planner_rows.html` (included via `{% include %}`). They are — Jinja2 includes inherit the parent context.

For the `filter_planner()` route, add `date` and `site` to the template context. Modify the return statement in `filter_planner()`:

```python
    return render_template("partials/planner_rows.html", results=results,
                           date=last.date_local.isoformat(), site=last.site_key)
```

- [ ] **Step 5: Verify manually by running the dev server**

Run: `docker-compose up -d` and navigate to the planner. Compute a session, verify the "Compare" column appears, click "Compare" on a target, verify the telescope comparison table loads.

- [ ] **Step 6: Run full test suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: ALL PASSED

- [ ] **Step 7: Commit**

```bash
git add app/templates/partials/telescope_compare.html app/templates/partials/planner_rows.html app/templates/partials/planner_table.html app/routes/planner.py
git commit -m "feat: add telescope comparison UI to session planner"
```

---

### Task 5: Composite Score Ordering & Edge Cases

**Files:**
- Modify: `tests/test_telescope_match.py`

This task adds the remaining test cases to ensure scoring and edge case behavior is correct.

- [ ] **Step 1: Write tests for score ordering and edge cases**

Append to `tests/test_telescope_match.py`:

```python
def test_composite_score_ordering(app):
    """A larger aperture telescope should score higher for a faint target,
    all else being equal at the same site."""
    from app.services.telescope_match import compare_telescopes

    with app.app_context():
        # Smaller aperture
        tel_small = _make_telescope(tel_id="T05", aperture=127, fov=60.0,
                                    filters=["L", "R", "G", "B"])
        rate_small = _make_rate(tel_small)
        # Larger aperture
        tel_large = _make_telescope(tel_id="T14", aperture=250, fov=60.0,
                                    filters=["L", "R", "G", "B"])
        rate_large = _make_rate(tel_large)
        db.session.add_all([tel_small, rate_small, tel_large, rate_large])
        db.session.commit()

        result = compare_telescopes(
            target=SAMPLE_TARGET, date=SAMPLE_DATE,
            moon_info={"phase_pct": 20.0, "separation_deg": 90.0, "risk": "G"},
        )

    viable = result["viable"]
    assert len(viable) == 2
    # Larger aperture should score higher (faster SNR, lower cost)
    assert viable[0]["telescope_id"] == "T14"
    assert viable[0]["score"] > viable[1]["score"]
```

- [ ] **Step 2: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_telescope_match.py::test_composite_score_ordering -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_telescope_match.py
git commit -m "test: add composite score ordering test for telescope match"
```

---

## File Summary

| File | Action | Purpose |
|------|--------|---------|
| `app/services/telescope_match.py` | Create | Core evaluation + comparison + scoring logic |
| `app/routes/planner.py` | Modify | Add `GET /planner/compare` route, update filter context |
| `app/templates/partials/telescope_compare.html` | Create | Comparison table partial (HTMX) |
| `app/templates/partials/planner_rows.html` | Modify | Add "Compare" button per row |
| `app/templates/partials/planner_table.html` | Modify | Add column header for Compare button |
| `tests/test_telescope_match.py` | Create | Unit + integration tests |
