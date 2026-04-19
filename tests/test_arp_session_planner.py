"""Tests for arp_session_planner.py pure helpers."""

import pytest
import ephem

from arp_common import SITE_UTAH
from arp_session_planner import (
    ephem_to_local,
    estimate_cost,
    assign_telescope,
    build_session_plan,
)


# ---------------------------------------------------------------------------
# ephem_to_local
# ---------------------------------------------------------------------------

def test_ephem_to_local_zero_offset():
    # ephem.Date("2026/04/15 12:00:00") with utc_offset=0 → "12:00"
    e = float(ephem.Date("2026/04/15 12:00:00"))
    assert ephem_to_local(e, 0) == "12:00"


def test_ephem_to_local_positive_offset():
    # UTC midnight + 2 hr offset → 02:00 local
    e = float(ephem.Date("2026/04/15 00:00:00"))
    assert ephem_to_local(e, 2) == "02:00"


def test_ephem_to_local_negative_offset():
    # UTC 12:00 - 7 hr = 05:00 local (New Mexico)
    e = float(ephem.Date("2026/04/15 12:00:00"))
    assert ephem_to_local(e, -7) == "05:00"


# ---------------------------------------------------------------------------
# estimate_cost
# ---------------------------------------------------------------------------

def test_estimate_cost_lrgb():
    """
    LRGB: sum([2,1,1,1]) × INTERVAL(300) = 1500 sec exposure
    + OVERHEAD_PER_TARGET_SECS(180) = 1680 sec = 28 min
    × rate(10) = 280 pts
    """
    assert estimate_cost("LRGB", 10) == 280


def test_estimate_cost_luminance():
    """
    Lum: sum([2]) × 300 = 600 sec exposure
    + 180 overhead = 780 sec = 13 min
    × 10 = 130 pts
    """
    assert estimate_cost("Luminance", 10) == 130


def test_estimate_cost_lrgb_costs_more_than_luminance():
    assert estimate_cost("LRGB", 10) > estimate_cost("Luminance", 10)


def test_estimate_cost_none_rate():
    assert estimate_cost("LRGB", None) is None


# ---------------------------------------------------------------------------
# assign_telescope (session planner's simpler version)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("size,expected", [
    (2.0,  "T17"),  # small tier
    (5.0,  "T11"),  # medium tier
    (10.0, "T5"),   # large tier
    (25.0, "T14"),  # very wide tier
])
def test_assign_telescope(size, expected):
    assert assign_telescope(size, SITE_UTAH) == expected


# ---------------------------------------------------------------------------
# build_session_plan
# ---------------------------------------------------------------------------

def _make_session_targets():
    """Two targets: one LRGB, one Luminance."""
    return [
        {
            "arp": 82, "name": "NGC 2535",
            "strategy": "LRGB", "size": 3.5,
            "telescope": "T11",
            "ra_dec": 8.187,  "dec_dec": 25.2,
            "hours": 4.5,
            "start_local": "20:00", "end_local": "00:30",
            "transit_local": "22:15",
            "transit_ephem": 0,
            "moon": {"phase": 10.0, "sep": 80.0, "risk": "G"},
            "cost_pts": 500,
        },
        {
            "arp": 1, "name": "NGC 2857",
            "strategy": "Luminance", "size": 5.2,
            "telescope": "T5",
            "ra_dec": 9.41,  "dec_dec": 49.35,
            "hours": 3.0,
            "start_local": "21:00", "end_local": "00:00",
            "transit_local": "22:30",
            "transit_ephem": 1,
            "moon": {"phase": 10.0, "sep": 75.0, "risk": "G"},
            "cost_pts": 200,
        },
    ]


def test_build_session_plan_required_directives():
    targets = _make_session_targets()
    plan = build_session_plan(targets, SITE_UTAH, "2026-04-15", "Plan-40")
    assert "#BillingMethod Session" in plan
    assert "#RESUME" in plan
    assert "#FIRSTLAST" in plan
    assert "#repeat 3" in plan
    assert "#shutdown" in plan


def test_build_session_plan_target_count_in_header():
    targets = _make_session_targets()
    plan = build_session_plan(targets, SITE_UTAH, "2026-04-15", "Plan-40")
    assert "Targets     : 2" in plan


def test_build_session_plan_uses_named_overhead_constants():
    """
    Regression guard: overhead_secs = N × 180 + 300.
    For 2 targets: overhead = 360 + 300 = 660 sec.
    Imaging:
      LRGB: sum([2,1,1,1]) × 300 = 1500 sec
      Lum:  sum([2]) × 300 = 600 sec
      Total imaging = 2100 sec
    Total duration = 2100 + 660 = 2760 sec = 46 min
    """
    targets = _make_session_targets()
    plan = build_session_plan(targets, SITE_UTAH, "2026-04-15", "Plan-40")
    # 46 minutes — check it appears in "Total duration" line
    assert "46m" in plan or "46 m" in plan


def test_build_session_plan_shows_plan_tier():
    targets = _make_session_targets()
    plan = build_session_plan(targets, SITE_UTAH, "2026-04-15", "Plan-90")
    assert "Plan-90" in plan
