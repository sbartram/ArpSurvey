"""Tests for the ACP plan generation service."""

import pytest
from app.services.acp import assign_telescope, build_plan, compute_lrgb_counts


def test_compute_lrgb_counts_default():
    counts = compute_lrgb_counts(2)
    assert counts == [2, 1, 1, 1]


def test_compute_lrgb_counts_count_4():
    counts = compute_lrgb_counts(4)
    assert counts == [4, 2, 2, 2]


def test_compute_lrgb_counts_count_1():
    counts = compute_lrgb_counts(1)
    assert counts == [1, 1, 1, 1]


def test_assign_telescope_compact_target():
    from arp_common import load_telescopes
    tels = load_telescopes()
    result = assign_telescope(1.5, "Spain", tels)
    assert result in ("T17", "T32", "T21", "T11", "T25")


def test_assign_telescope_preferred_override():
    from arp_common import load_telescopes
    tels = load_telescopes()
    result = assign_telescope(1.5, "Spain", tels, preferred_telescope="T20")
    assert result == "T20"


def test_assign_telescope_preferred_invalid_falls_back():
    from arp_common import load_telescopes
    tels = load_telescopes()
    result = assign_telescope(1.5, "Spain", tels, preferred_telescope="TXYZ")
    assert result in ("T17", "T32", "T21", "T11", "T25")


def test_build_plan_produces_valid_acp():
    targets = [
        {"arp": 85, "name": "M51", "ra_hours": 13.5, "dec_degrees": 47.2,
         "size_arcmin": 11.0, "filter_strategy": "LRGB"},
    ]
    params = {"exposure": 300, "count": 2, "repeat": 3,
              "plan_tier": "Plan-40", "binning": 1}
    result = build_plan(targets, "T20", "Spring", params)

    assert "filename" in result
    assert "content" in result
    assert "duration_secs" in result
    assert "cost_points" in result
    assert "#shutdown" in result["content"]
    assert "Arp085_M51" in result["content"]
    assert "#BillingMethod Session" in result["content"]
    assert "#repeat 3" in result["content"]
