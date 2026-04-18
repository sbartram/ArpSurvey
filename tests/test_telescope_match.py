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


def test_evaluate_telescope_below_horizon(app):
    """A high-Dec northern target should be disqualified from Australia."""
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
        tel = _make_telescope(fov=60.0)
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
        tel = _make_telescope(filters=["L"])
        db.session.add(tel)
        db.session.commit()

        result = evaluate_telescope(
            target=SAMPLE_TARGET, telescope=tel, date=SAMPLE_DATE,
            site_key="New Mexico",
            moon_info={"phase_pct": 20.0, "separation_deg": 90.0, "risk": "G"},
        )

    assert result["disqualified"] is True
    assert "filter" in result["disqualification_reason"].lower()


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
