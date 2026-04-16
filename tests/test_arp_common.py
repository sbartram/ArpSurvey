"""Tests for arp_common.py pure functions."""

import pytest

from arp_common import (
    moon_risk,
    parse_ra,
    parse_dec,
    sanitize_name,
    parse_catalog_coords,
    RISK_LABELS,
)


# ---------------------------------------------------------------------------
# moon_risk
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phase,sep,expected", [
    # phase < 25 → min_sep=20, GOOD_MARGIN=20 → good ≥ 40, marginal 20..39, avoid < 20
    (10, 45, "G"),   # margin=25, good
    (10, 25, "M"),   # margin=5, marginal
    (10, 15, "A"),   # margin=-5, avoid
    (24.9, 20, "M"), # still in <25 bin (min=20, margin=0 → marginal)
    # phase < 50 → min_sep=40 → good ≥ 60, marginal 40..59, avoid < 40
    (25, 40, "M"),   # now in <50 bin, min=40, margin=0
    (30, 65, "G"),   # margin=25, good
    # phase < 75 → min_sep=60 → good ≥ 80, marginal 60..79
    (60, 85, "G"),   # margin=25, good
    (60, 65, "M"),   # margin=5, marginal
    # phase < 101 → min_sep=90 → good ≥ 110, marginal 90..109
    (100, 100, "M"), # margin=10, marginal
    (100, 60, "A"),  # margin=-30, avoid
    (100, 115, "G"), # margin=25, good
])
def test_moon_risk(phase, sep, expected):
    assert moon_risk(phase, sep) == expected


def test_moon_risk_returns_short_codes_not_long():
    """Regression guard for Bug 4: moon_risk must return single-letter codes."""
    assert moon_risk(50, 80) == "G"
    assert moon_risk(50, 80) != "Good"


# ---------------------------------------------------------------------------
# parse_ra
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("input_str,expected", [
    ("12 34 56", "12:34:56"),
    ("12:34:56", "12:34:56"),      # idempotent on colon form
    ("  12 34 56  ", "12:34:56"),  # leading/trailing whitespace stripped
    ("00 00 00", "00:00:00"),
])
def test_parse_ra(input_str, expected):
    assert parse_ra(input_str) == expected


# ---------------------------------------------------------------------------
# parse_dec
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("input_str,expected", [
    ("+45 30.5", "+45:30:30"),  # 0.5 min → 30 sec
    ("-12 15.0", "-12:15:00"),
    ("45 30.5",  "+45:30:30"),  # no sign defaults to +
    ("+0 00.0",  "+0:00:00"),
])
def test_parse_dec_two_part(input_str, expected):
    assert parse_dec(input_str) == expected


def test_parse_dec_three_part_returns_unchanged():
    """Function only handles 2-part input; 3-part returns as-is."""
    assert parse_dec("+45 30 15") == "+45 30 15"


# ---------------------------------------------------------------------------
# sanitize_name
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("input_str,expected", [
    ("NGC 1234", "NGC_1234"),
    ("NGC 2535 + 56", "NGC_2535_+_56"),
    ("a   b", "a_b"),           # multiple spaces collapsed
    ("_foo_", "foo"),           # edge underscores stripped
    ("Stephan's Quint", "Stephan_s_Quint"),  # apostrophe → underscore
    ("NGC-1234", "NGC-1234"),   # hyphens preserved
])
def test_sanitize_name(input_str, expected):
    assert sanitize_name(input_str) == expected


# ---------------------------------------------------------------------------
# parse_catalog_coords
# ---------------------------------------------------------------------------

def test_parse_catalog_coords_positive():
    ra_deg, dec_deg = parse_catalog_coords("12 34 56", "+45 30")
    # RA: (12 + 34/60 + 56/3600) × 15 = 12.58222... × 15 = 188.73333...
    assert ra_deg == pytest.approx(188.73333, abs=1e-4)
    assert dec_deg == pytest.approx(45.5)


def test_parse_catalog_coords_negative():
    ra_deg, dec_deg = parse_catalog_coords("03 15 00", "-25 00")
    # RA: (3 + 15/60 + 0/3600) × 15 = 3.25 × 15 = 48.75
    assert ra_deg == pytest.approx(48.75)
    assert dec_deg == pytest.approx(-25.0)


def test_parse_catalog_coords_two_part_ra():
    """If only HH MM provided, seconds default to 0."""
    ra_deg, dec_deg = parse_catalog_coords("12 34", "+45 30")
    # RA: (12 + 34/60) × 15 = 12.566... × 15 = 188.5
    assert ra_deg == pytest.approx(188.5, abs=1e-4)
    assert dec_deg == pytest.approx(45.5)


# ---------------------------------------------------------------------------
# RISK_LABELS
# ---------------------------------------------------------------------------

def test_risk_labels_complete():
    assert RISK_LABELS == {"G": "Good", "M": "Marginal", "A": "Avoid"}


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

import pandas as pd

from arp_common import (
    load_targets, load_telescopes, load_rates, load_ned_coords,
    PLAN_TIERS,
)


def test_load_targets_default_sheet():
    df = load_targets()
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 300  # Arp catalog has 338 objects
    # All column names should be stripped of whitespace
    for col in df.columns:
        assert col == col.strip()
    # Key columns must be present
    assert "Arp #" in df.columns
    assert "Common Name" in df.columns
    assert "RA (J2000)" in df.columns
    assert "Dec (J2000)" in df.columns
    assert "Size (arcmin)" in df.columns


def test_load_targets_spring_sheet_is_subset():
    """Spring (Now) sheet has RA 8h-14h targets — fewer than All Objects."""
    all_df = load_targets()
    spring_df = load_targets(sheet_name="Spring (Now)")
    assert len(spring_df) < len(all_df)
    assert len(spring_df) > 50  # has ~149 targets


def test_load_targets_missing_sheet_raises():
    """Nonexistent sheet name must raise (type of exception varies by pandas/openpyxl)."""
    with pytest.raises(Exception):
        load_targets(sheet_name="Definitely Not A Sheet Name")


def test_load_telescopes_structure():
    df = load_telescopes()
    assert isinstance(df, pd.DataFrame)
    assert "T11" in df.index  # known iTelescope in the fleet
    assert "FOV X (arcmins)" in df.columns
    assert "FOV Y (arcmins)" in df.columns


def test_load_rates_nested_structure():
    rates = load_rates()
    assert isinstance(rates, dict)
    assert len(rates) > 0
    for tel_id, tel_rates in rates.items():
        assert tel_id.startswith("T")
        assert set(tel_rates.keys()) == {"session", "exposure"}
        for billing_mode in ("session", "exposure"):
            # Every plan tier should be a key
            for plan in PLAN_TIERS:
                assert plan in tel_rates[billing_mode]


def test_load_rates_values_are_float_or_none():
    """Bug 1 regression guard: invalid rate values must not raise, must become None."""
    rates = load_rates()
    for tel_id, tel_rates in rates.items():
        for billing_mode in ("session", "exposure"):
            for plan, value in tel_rates[billing_mode].items():
                assert value is None or isinstance(value, float), \
                    f"{tel_id}.{billing_mode}.{plan} = {value!r} (type: {type(value).__name__})"


def test_load_ned_coords_present():
    """arp_ned_coords.csv exists in repo — should load successfully."""
    coords = load_ned_coords()
    assert isinstance(coords, dict)
    assert len(coords) > 300  # most of 338 targets
    # Each value is (ra_hours, dec_deg)
    for arp_num, (ra_h, dec_d) in coords.items():
        assert isinstance(arp_num, int)
        assert 0 <= ra_h < 24
        assert -90 <= dec_d <= 90


def test_load_ned_coords_missing_file(monkeypatch, tmp_path):
    """If arp_ned_coords.csv doesn't exist, return empty dict (no exception)."""
    # Point DATA_DIR to an empty tmp directory
    import arp_common
    monkeypatch.setattr(arp_common, "DATA_DIR", tmp_path)
    assert arp_common.load_ned_coords() == {}
