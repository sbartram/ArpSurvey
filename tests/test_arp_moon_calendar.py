"""Tests for arp_moon_calendar.py helpers."""

import datetime
import math

import pytest

from arp_moon_calendar import build_observer, calc_windows


# ---------------------------------------------------------------------------
# build_observer
# ---------------------------------------------------------------------------

def test_build_observer_new_mexico():
    obs, utc_offset = build_observer("New Mexico")
    assert utc_offset == -7
    # ephem lat/lon are in radians — convert back to degrees for assertion
    assert math.degrees(float(obs.lat)) == pytest.approx(33.0, abs=0.01)
    assert math.degrees(float(obs.lon)) == pytest.approx(-107.0, abs=0.01)
    assert obs.elevation == 1400


def test_build_observer_spain():
    obs, utc_offset = build_observer("Spain")
    assert utc_offset == 2
    assert math.degrees(float(obs.lat)) == pytest.approx(38.0, abs=0.01)


def test_build_observer_australia_negative_lat():
    obs, utc_offset = build_observer("Australia")
    assert utc_offset == 10
    assert math.degrees(float(obs.lat)) == pytest.approx(-31.3, abs=0.01)


# ---------------------------------------------------------------------------
# calc_windows
# ---------------------------------------------------------------------------

def test_calc_windows_structure():
    """3-day window → list of 3 dicts with correct keys."""
    start = datetime.date(2026, 5, 1)
    # RA/Dec in ephem format (colon-separated)
    windows = calc_windows("12:00:00", "+30:00:00", "New Mexico", start, 3)
    assert len(windows) == 3
    for w in windows:
        assert set(w.keys()) == {"d", "p", "s", "r"}
        assert w["r"] in ("G", "M", "A")
        assert 0 <= w["p"] <= 100
        assert 0 <= w["s"] <= 180


def test_calc_windows_date_sequence():
    """Dates are consecutive starting from start_date."""
    start = datetime.date(2026, 5, 1)
    windows = calc_windows("12:00:00", "+30:00:00", "New Mexico", start, 5)
    dates = [w["d"] for w in windows]
    assert dates == [
        "2026-05-01", "2026-05-02", "2026-05-03",
        "2026-05-04", "2026-05-05",
    ]
