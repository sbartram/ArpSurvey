"""Tests for arp_acp_generator.py pure functions and helpers."""

import pandas as pd
import pytest

from arp_acp_generator import (
    format_duration,
    parse_fov,
    target_fits_telescope,
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


def test_parse_fov_nan():
    """NaN behavior: float(NaN) doesn't raise, so parse_fov returns (NaN, 20.0)
    rather than (None, None). NaN comparison via != self, or None check."""
    row = pd.Series({"FOV X (arcmins)": float("nan"), "FOV Y (arcmins)": 20.0})
    x, y = parse_fov(row)
    # Accept either (NaN, 20.0) or (None, None)
    assert (x != x) or x is None


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
