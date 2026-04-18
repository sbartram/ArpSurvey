"""Tests for SQLAlchemy models."""

import pytest
from datetime import date, datetime, timezone
from app import create_app, db
from app.config import Config
from app.models import (
    Target, Telescope, TelescopeRate, ImagingLog,
    MoonData, MoonCalendarRun, SessionResult, GeneratedPlan,
)


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


@pytest.fixture
def session(app):
    with app.app_context():
        yield db.session


def test_target_create_and_query(session):
    t = Target(arp_number=1, name="NGC 2857", ra_hours=9.37, dec_degrees=49.35,
               season="Spring", status="Pending")
    session.add(t)
    session.commit()
    result = session.query(Target).filter_by(arp_number=1).first()
    assert result.name == "NGC 2857"
    assert result.status == "Pending"


def test_target_best_ra_prefers_ned(session):
    t = Target(arp_number=1, name="Test", ra_hours=9.0, dec_degrees=49.0,
               ned_ra_hours=9.1, ned_dec_degrees=49.1, season="Spring")
    session.add(t)
    session.commit()
    assert t.best_ra == 9.1
    assert t.best_dec == 49.1


def test_target_best_ra_falls_back_to_catalog(session):
    t = Target(arp_number=2, name="Test", ra_hours=9.0, dec_degrees=49.0,
               season="Spring")
    session.add(t)
    session.commit()
    assert t.best_ra == 9.0
    assert t.best_dec == 49.0


def test_target_arp_number_unique(session):
    t1 = Target(arp_number=1, name="A", ra_hours=1.0, dec_degrees=1.0, season="Spring")
    t2 = Target(arp_number=1, name="B", ra_hours=2.0, dec_degrees=2.0, season="Spring")
    session.add(t1)
    session.commit()
    session.add(t2)
    with pytest.raises(Exception):
        session.commit()


def test_telescope_and_rate(session):
    tel = Telescope(telescope_id="T17", site="Spain", fov_arcmin=20.5)
    session.add(tel)
    session.commit()
    rate = TelescopeRate(telescope_id=tel.id, plan_tier="Plan-40",
                         session_rate=102.0, exposure_rate=85.0)
    session.add(rate)
    session.commit()
    assert tel.rates.first().plan_tier == "Plan-40"


def test_imaging_log_with_foreign_keys(session):
    target = Target(arp_number=85, name="M51", ra_hours=13.5, dec_degrees=47.2,
                    season="Spring")
    tel = Telescope(telescope_id="T11", site="New Mexico")
    session.add_all([target, tel])
    session.commit()
    log = ImagingLog(target_id=target.id, date_imaged=date(2026, 4, 15),
                     telescope_id=tel.id, filter_strategy="LRGB",
                     exposure_minutes=90, quality=4)
    session.add(log)
    session.commit()
    assert log.target.name == "M51"
    assert log.telescope.telescope_id == "T11"


def test_moon_data_unique_constraint(session):
    target = Target(arp_number=1, name="Test", ra_hours=1.0, dec_degrees=1.0,
                    season="Spring")
    session.add(target)
    session.commit()
    m1 = MoonData(target_id=target.id, night_date=date(2026, 4, 17),
                  phase_pct=45.0, separation_deg=80.0, risk="G")
    m2 = MoonData(target_id=target.id, night_date=date(2026, 4, 17),
                  phase_pct=45.0, separation_deg=80.0, risk="G")
    session.add(m1)
    session.commit()
    session.add(m2)
    with pytest.raises(Exception):
        session.commit()


def test_moon_calendar_run(session):
    run = MoonCalendarRun(
        status="computing", days=90, site_key="New Mexico",
        start_date=date(2026, 4, 17),
        phase_calendar=[{"date": "2026-04-17", "phase_pct": 45.0}],
    )
    session.add(run)
    session.commit()
    assert run.status == "computing"
    assert run.phase_calendar[0]["phase_pct"] == 45.0


def test_generated_plan(session):
    plan = GeneratedPlan(
        filename="Arp_Spring_T17_batch01.txt", plan_type="acp",
        content="; test plan\n#shutdown", season="Spring",
        metadata_={"exposure": 300, "repeat": 3},
    )
    session.add(plan)
    session.commit()
    assert plan.metadata_["exposure"] == 300
