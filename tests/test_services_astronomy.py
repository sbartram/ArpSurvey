"""Tests for the astronomy service layer."""

import datetime
import pytest
from arp_common import SITE_UTAH, SITE_SPAIN
from app.services.astronomy import build_observer, dark_window, moon_info


def test_build_observer_utah():
    obs = build_observer(SITE_UTAH, datetime.date(2026, 4, 17))
    assert obs is not None
    assert float(obs.lat) == pytest.approx(0.665, abs=0.01)


def test_dark_window_returns_datetimes():
    eve, morn = dark_window(SITE_UTAH, datetime.date(2026, 4, 17))
    assert isinstance(eve, datetime.datetime)
    assert isinstance(morn, datetime.datetime)
    assert morn > eve
    hours = (morn - eve).total_seconds() / 3600
    assert 7 < hours < 12


def test_dark_window_spain():
    eve, morn = dark_window(SITE_SPAIN, datetime.date(2026, 6, 21))
    assert morn > eve
    hours = (morn - eve).total_seconds() / 3600
    assert 4 < hours < 10


def test_moon_info_returns_phase_sep_risk():
    obs = build_observer(SITE_UTAH, datetime.date(2026, 4, 17))
    info = moon_info(13.5, 47.2, obs)
    assert "phase_pct" in info
    assert "separation_deg" in info
    assert "risk" in info
    assert info["risk"] in ("G", "M", "A")
    assert 0 <= info["phase_pct"] <= 100
    assert 0 <= info["separation_deg"] <= 180
