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
