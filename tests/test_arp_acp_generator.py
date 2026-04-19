"""Tests for arp_acp_generator.py pure functions and helpers."""

import pandas as pd
import pytest

from arp_acp_generator import (
    format_duration,
    parse_fov,
    target_fits_telescope,
    assign_telescope,
)


# ---------------------------------------------------------------------------
# format_duration
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("secs,expected", [
    (0,    "0m"),
    (90,   "1m"),
    (3600, "1h 00m"),
    (5430, "1h 30m"),
    (7200, "2h 00m"),
    (59,   "0m"),    # under a minute rounds down
])
def test_format_duration(secs, expected):
    assert format_duration(secs) == expected


# ---------------------------------------------------------------------------
# parse_fov
# ---------------------------------------------------------------------------

def test_parse_fov_valid_numeric():
    row = pd.Series({"FOV X (arcmins)": 30.0, "FOV Y (arcmins)": 20.0})
    assert parse_fov(row) == (30.0, 20.0)


def test_parse_fov_nan_passes_through():
    """NaN passes through as NaN (float(nan) doesn't raise). This is harmless
    because target_fits_telescope treats NaN comparisons as False."""
    import math
    row = pd.Series({"FOV X (arcmins)": float("nan"), "FOV Y (arcmins)": 20.0})
    x, y = parse_fov(row)
    assert math.isnan(x)
    assert y == 20.0


def test_parse_fov_nan_end_to_end_returns_false():
    """End-to-end contract: regardless of NaN vs None in parse_fov output,
    target_fits_telescope must return False for unknown FOV."""
    row = pd.Series({"FOV X (arcmins)": float("nan"), "FOV Y (arcmins)": 20.0})
    fov_x, fov_y = parse_fov(row)
    assert target_fits_telescope(5, fov_x, fov_y) is False


def test_parse_fov_string_placeholder():
    row = pd.Series({"FOV X (arcmins)": "?", "FOV Y (arcmins)": "?"})
    assert parse_fov(row) == (None, None)


# ---------------------------------------------------------------------------
# target_fits_telescope
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("size,fov_x,fov_y,expected", [
    (10, 30, 20, True),    # 10 × 1.5 = 15, fits in 20
    (14, 20, 20, False),   # 14 × 1.5 = 21, doesn't fit in 20
    (5,  30, 20, True),    # 5 × 1.5 = 7.5, easily fits
    (15, 30, 20, False),   # 15 × 1.5 = 22.5, doesn't fit (min fov=20)
    (5,  None, None, False),  # None FOV never fits
    (5,  None, 20,   False),  # either None → False
])
def test_target_fits_telescope(size, fov_x, fov_y, expected):
    assert target_fits_telescope(size, fov_x, fov_y) == expected


def test_target_fits_telescope_custom_margin():
    """Margin defaults to 1.5 but is parameter-accepting."""
    # size=10, fov=15: 10 × 1.0 = 10 ≤ 15 with margin=1.0
    assert target_fits_telescope(10, 15, 15, margin=1.0) is True
    # Same with default margin=1.5: 10 × 1.5 = 15 ≤ 15 → True (≤, not <)
    assert target_fits_telescope(10, 15, 15) is True
    # With margin=2.0: 10 × 2 = 20 > 15 → False
    assert target_fits_telescope(10, 15, 15, margin=2.0) is False


# ---------------------------------------------------------------------------
# assign_telescope
# ---------------------------------------------------------------------------


def _make_telescope_df():
    """Build a minimal telescope DataFrame covering the tier preferences."""
    return pd.DataFrame({
        "FOV X (arcmins)": [23, 30, 40, 70, 90, 120],
        "FOV Y (arcmins)": [15, 20, 30, 50, 65, 85],
    }, index=["T17", "T11", "T21", "T5", "T14", "T8"])


def test_assign_telescope_explicit_override():
    telescopes = _make_telescope_df()
    row = pd.Series({"Size (arcmin)": 5.0, "Best Site": "New Mexico"})
    assert assign_telescope(row, telescopes, preferred_telescope="T11") == "T11"


def test_assign_telescope_small_target_prefers_small_tier():
    """Size < 3 arcmin → site-preferred telescope from small tier that fits."""
    telescopes = _make_telescope_df()
    row = pd.Series({"Size (arcmin)": 2.0, "Best Site": "New Mexico"})
    # Small tier is ["T17", "T32", "T21", "T11", "T25"]
    # New Mexico site preference: T21, T11, T25 come before T17 (Spain)
    # T21 FOV min=30; 2 × 1.5 = 3 ≤ 30 → fits → T21 selected
    assert assign_telescope(row, telescopes) == "T21"


def test_assign_telescope_large_target_uses_large_tier():
    """Size 7-20 arcmin → large tier."""
    telescopes = _make_telescope_df()
    row = pd.Series({"Size (arcmin)": 10.0, "Best Site": "New Mexico"})
    # Large tier is ["T5", "T20", "T26", "T71", "T75"]
    # T5 FOV min=50; 10 × 1.5 = 15 ≤ 50 → T5 selected
    assert assign_telescope(row, telescopes) == "T5"


def test_assign_telescope_very_large_target():
    """Size > 20 arcmin → very-wide tier."""
    telescopes = _make_telescope_df()
    row = pd.Series({"Size (arcmin)": 25.0, "Best Site": "New Mexico"})
    # Very-wide tier starts with ["T14", "T8", ...]
    # T14 FOV min=65; 25 × 1.5 = 37.5 ≤ 65 → T14 selected
    assert assign_telescope(row, telescopes) == "T14"


def test_assign_telescope_missing_size_defaults_to_3():
    """Invalid size falls back to 3.0 arcmin → small/medium tier."""
    telescopes = _make_telescope_df()
    row = pd.Series({"Size (arcmin)": "invalid", "Best Site": "New Mexico"})
    # Size defaults to 3.0 → medium tier (3.0 < 7.0)
    # Medium tier is ["T11", "T21", "T26", "T30", "T17"]
    # T11 FOV min=20; 3 × 1.5 = 4.5 ≤ 20 → T11 selected
    result = assign_telescope(row, telescopes)
    assert result in ("T11", "T21", "T17")  # any of the medium-tier fits


# ---------------------------------------------------------------------------
# calc_plan_duration
# ---------------------------------------------------------------------------

from arp_acp_generator import calc_plan_duration, calc_plan_cost


def _make_batch(strategies):
    """Build a DataFrame with one row per strategy string."""
    return pd.DataFrame({
        "Arp #": list(range(1, len(strategies) + 1)),
        "Common Name": [f"Target{i}" for i in range(1, len(strategies) + 1)],
        "Filter Strategy": strategies,
    })


def test_calc_plan_duration_single_luminance():
    """
    1 Lum target, interval=300, repeat=3, lum_counts=[2]:
      exposure_secs = 1 × 2 × 300 = 600
      imaging_total (returned) = 600 × 3 = 1800
      target_overhead = 1 × 180 = 180
      total_secs = (600 + 180) × 3 + 300 = 2640
    """
    batch = _make_batch(["Luminance"])
    total, imaging = calc_plan_duration(
        batch, interval=300, repeat=3,
        lrgb_counts=[2, 1, 1, 1], lum_counts=[2],
    )
    assert total == 2640
    assert imaging == 1800


def test_calc_plan_duration_single_lrgb():
    """
    1 LRGB target, interval=300, repeat=3, lrgb_counts=[2,1,1,1]:
      exposures per target = 2+1+1+1 = 5
      exposure_secs = 1 × 5 × 300 = 1500
      imaging_total = 1500 × 3 = 4500
      target_overhead = 1 × 180 = 180
      total = (1500 + 180) × 3 + 300 = 5340
    """
    batch = _make_batch(["LRGB"])
    total, imaging = calc_plan_duration(
        batch, interval=300, repeat=3,
        lrgb_counts=[2, 1, 1, 1], lum_counts=[2],
    )
    assert total == 5340
    assert imaging == 4500


def test_calc_plan_duration_mixed_batch():
    """
    2 LRGB + 1 Lum, interval=300, repeat=3:
      exposure_secs = (2 × 5 × 300) + (1 × 2 × 300) = 3000 + 600 = 3600
      imaging_total = 3600 × 3 = 10800
      target_overhead = 3 × 180 = 540
      total = (3600 + 540) × 3 + 300 = 12720
    """
    batch = _make_batch(["LRGB", "LRGB", "Luminance"])
    total, imaging = calc_plan_duration(
        batch, interval=300, repeat=3,
        lrgb_counts=[2, 1, 1, 1], lum_counts=[2],
    )
    assert total == 12720
    assert imaging == 10800


# ---------------------------------------------------------------------------
# calc_plan_cost
# ---------------------------------------------------------------------------

def test_calc_plan_cost_session_mode():
    """
    Session billing = total_secs / 3600 × rate.
    1 Lum target: total = 2640 sec = 0.733 hr. At 10 pts/hr → 7.3 pts.
    """
    batch = _make_batch(["Luminance"])
    rates = {"T11": {"session": {"Plan-40": 10.0}, "exposure": {"Plan-40": 5.0}}}
    points, rate = calc_plan_cost(
        batch, "T11", interval=300, repeat=3,
        lrgb_counts=[2, 1, 1, 1], lum_counts=[2],
        rates=rates, plan_tier="Plan-40", billing_mode="session",
    )
    assert points == pytest.approx(7.3, abs=0.1)
    assert rate == 10.0


def test_calc_plan_cost_exposure_mode():
    """
    Exposure billing = imaging_secs / 3600 × rate.
    1 Lum target: imaging = 1800 sec = 0.5 hr. At 5 pts/hr → 2.5 pts.
    """
    batch = _make_batch(["Luminance"])
    rates = {"T11": {"session": {"Plan-40": 10.0}, "exposure": {"Plan-40": 5.0}}}
    points, rate = calc_plan_cost(
        batch, "T11", interval=300, repeat=3,
        lrgb_counts=[2, 1, 1, 1], lum_counts=[2],
        rates=rates, plan_tier="Plan-40", billing_mode="exposure",
    )
    assert points == pytest.approx(2.5)
    assert rate == 5.0


def test_calc_plan_cost_free_telescope():
    """Rate of 0 means free telescope (e.g. T33, T68)."""
    batch = _make_batch(["Luminance"])
    rates = {"T68": {"session": {"Plan-40": 0.0}, "exposure": {"Plan-40": 0.0}}}
    points, rate = calc_plan_cost(
        batch, "T68", interval=300, repeat=3,
        lrgb_counts=[2, 1, 1, 1], lum_counts=[2],
        rates=rates, plan_tier="Plan-40", billing_mode="session",
    )
    assert points == 0.0
    assert rate == 0.0


def test_calc_plan_cost_missing_telescope():
    """Telescope not in rates → (None, None)."""
    batch = _make_batch(["Luminance"])
    rates = {}
    points, rate = calc_plan_cost(
        batch, "T11", interval=300, repeat=3,
        lrgb_counts=[2, 1, 1, 1], lum_counts=[2],
        rates=rates, plan_tier="Plan-40", billing_mode="session",
    )
    assert points is None
    assert rate is None


# ---------------------------------------------------------------------------
# build_acp_header
# ---------------------------------------------------------------------------

from arp_acp_generator import build_acp_header, build_target_block


def test_build_acp_header_contains_basics():
    header = build_acp_header(
        plan_name="Arp_Spring_T11_batch01",
        telescope_id="T11",
        season="Spring",
        target_count=5,
    )
    assert "Arp_Spring_T11_batch01" in header
    assert "T11" in header
    assert "Spring" in header
    assert "Targets      : 5" in header


def test_build_acp_header_free_cost():
    header = build_acp_header(
        plan_name="test",
        telescope_id="T68",
        season="Spring",
        target_count=1,
        duration_str="1h 00m",
        imaging_time_str="0h 30m",
        session_cost=0.0,
        exposure_cost=0.0,
        plan_tier="Plan-40",
    )
    assert "FREE" in header


def test_build_acp_header_no_plan_tier_omits_cost_block():
    """Without plan_tier, no 'Est. Cost' block appears."""
    header = build_acp_header(
        plan_name="test",
        telescope_id="T11",
        season="Spring",
        target_count=1,
        duration_str="1h 00m",
    )
    assert "Est. Cost" not in header


def test_build_acp_header_cost_formatted():
    header = build_acp_header(
        plan_name="test",
        telescope_id="T11",
        season="Spring",
        target_count=1,
        duration_str="1h 00m",
        imaging_time_str="0h 30m",
        session_cost=1234.0,
        exposure_cost=567.0,
        plan_tier="Plan-40",
    )
    assert "Session billing : ~1234 pts" in header
    assert "Exposure billing: ~567 pts" in header


# ---------------------------------------------------------------------------
# build_target_block
# ---------------------------------------------------------------------------

def test_build_target_block_lrgb():
    row = pd.Series({
        "Arp #": 82,
        "Common Name": "NGC 2535",
        "Size (arcmin)": 3.5,
        "RA (J2000)": "08 11 13",
        "Dec (J2000)": "+25 12",
    })
    block = build_target_block(
        row, filter_strategy="LRGB",
        interval=300, lrgb_counts=[2, 1, 1, 1], lum_counts=[2],
    )
    assert "#filter Luminance,Red,Green,Blue" in block
    assert "#binning 1,2,2,2" in block
    assert "#count 2,1,1,1" in block
    assert "#interval 300,300,300,300" in block
    assert "Arp 82: NGC 2535" in block


def test_build_target_block_luminance():
    row = pd.Series({
        "Arp #": 82,
        "Common Name": "NGC 2535",
        "Size (arcmin)": 3.5,
        "RA (J2000)": "08 11 13",
        "Dec (J2000)": "+25 12",
    })
    block = build_target_block(
        row, filter_strategy="Luminance",
        interval=300, lrgb_counts=[2, 1, 1, 1], lum_counts=[2],
    )
    # Verify Luminance-only directives
    assert "#filter Luminance" in block
    # Should NOT contain LRGB filter list
    assert "Luminance,Red" not in block
    assert "#binning 1\n" in block


def test_build_target_block_uses_ned_coords_when_available():
    """NED coords override parsed catalog coords when provided."""
    row = pd.Series({
        "Arp #": 82,
        "Common Name": "NGC 2535",
        "Size (arcmin)": 3.5,
        "RA (J2000)": "08 11 13",
        "Dec (J2000)": "+25 12",
    })
    ned_coords = {82: (9.999999, 30.0)}  # obviously wrong values vs. catalog
    block = build_target_block(
        row, filter_strategy="Luminance",
        interval=300, lrgb_counts=[2, 1, 1, 1], lum_counts=[2],
        ned_coords=ned_coords,
    )
    # The NED coords should appear in the coordinate line
    assert "9.999999" in block
    assert "30.000000" in block
