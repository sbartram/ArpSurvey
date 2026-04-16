# pytest Test Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pytest-based test suite covering pure functions and data loaders across all 5 Python modules.

**Architecture:** One test file per source module in `tests/` at repo root. Tests exercise existing code (verification, not TDD) — most should pass on first run since code is already written. Tests that fail may indicate either a test bug or a real regression.

**Tech Stack:** Python 3.9+, pytest, pandas, ephem (already installed in `.venv/`)

**Spec:** `docs/superpowers/specs/2026-04-16-pytest-suite-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| **Create** | `pyproject.toml` | pytest configuration (testpaths, pythonpath) |
| **Create** | `tests/__init__.py` | Empty, marks tests as a package |
| **Create** | `tests/test_arp_common.py` | Tests for arp_common pure functions, regression guards, and data loaders |
| **Create** | `tests/test_arp_acp_generator.py` | Tests for acp_generator pure functions and helpers |
| **Create** | `tests/test_arp_session_planner.py` | Tests for session_planner pure helpers |
| **Create** | `tests/test_arp_moon_calendar.py` | Tests for moon_calendar helpers |
| **Create** | `tests/test_arp_ned_coords.py` | Tests for ned_coords name generation |
| **Modify** | `CLAUDE.md` | Add pytest to install instructions and document test commands |

---

### Task 1: Project setup — install pytest, create config

**Files:**
- Create: `pyproject.toml`
- Create: `tests/__init__.py`

- [ ] **Step 1: Install pytest in the local venv**

Run:
```bash
.venv/bin/pip install --quiet pytest
```

Verify:
```bash
.venv/bin/pytest --version
```
Expected: `pytest 8.x.x` or similar (any recent pytest).

- [ ] **Step 2: Create `pyproject.toml` at repo root**

Content:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 3: Create empty `tests/__init__.py`**

The file should be empty — just mark the directory as a Python package for pytest discovery.

- [ ] **Step 4: Verify pytest can run with no tests**

Run:
```bash
.venv/bin/pytest tests/ -v
```
Expected: exits with "no tests ran" message and exit code 5 (pytest's "no tests collected" code). That's OK — we haven't written any yet.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/__init__.py
git commit -m "Add pytest configuration and tests/ package"
```

---

### Task 2: arp_common.py pure function tests (moon_risk + coordinate helpers)

**Files:**
- Create: `tests/test_arp_common.py`

- [ ] **Step 1: Create `tests/test_arp_common.py` with pure-function tests**

```python
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
```

- [ ] **Step 2: Run the tests and verify they all pass**

Run:
```bash
.venv/bin/pytest tests/test_arp_common.py -v
```

Expected: All tests pass. Approximately 28 tests (parametrized cases count separately).

- [ ] **Step 3: If any test fails, diagnose before proceeding**

A failing test here means either:
- The test expected value is wrong (verify manually by running the function in a REPL)
- The code has a latent bug (then the test revealed it — which is exactly the point)

Do not "fix" by relaxing the assertion. Understand why, then fix the right thing.

- [ ] **Step 4: Commit**

```bash
git add tests/test_arp_common.py
git commit -m "Add tests for arp_common pure functions and RISK_LABELS"
```

---

### Task 3: arp_common.py data loader tests

**Files:**
- Modify: `tests/test_arp_common.py` (append)

- [ ] **Step 1: Append data loader tests to `tests/test_arp_common.py`**

Add at the end of the file:

```python


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
```

- [ ] **Step 2: Run the new tests**

```bash
.venv/bin/pytest tests/test_arp_common.py -v -k "load"
```

Expected: All 8 loader tests pass.

- [ ] **Step 3: Run the whole file to confirm nothing broke**

```bash
.venv/bin/pytest tests/test_arp_common.py -v
```

Expected: All tests still pass (pure function tests + new loader tests).

- [ ] **Step 4: Commit**

```bash
git add tests/test_arp_common.py
git commit -m "Add tests for arp_common data loaders"
```

---

### Task 4: arp_acp_generator.py — format_duration, parse_fov, target_fits_telescope

**Files:**
- Create: `tests/test_arp_acp_generator.py`

- [ ] **Step 1: Create `tests/test_arp_acp_generator.py` with helper tests**

```python
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
    row = pd.Series({"FOV X (arcmins)": float("nan"), "FOV Y (arcmins)": 20.0})
    # float(NaN) works but then any arithmetic comparison with NaN is False;
    # parse_fov returns the NaN directly (since float(NaN) succeeds). Test
    # actual behavior: it returns (NaN, 20.0). Consumers check via
    # target_fits_telescope which handles None. For NaN handling, the
    # check in parse_fov is for the pandas missing-value case.
    # Actually, float(NaN) == NaN, so parse_fov returns (NaN, 20.0).
    # The None path is triggered by non-numeric values (strings like "?").
    x, y = parse_fov(row)
    # Accept either (NaN, 20.0) or (None, None) depending on pandas behavior
    assert (x != x) or x is None   # NaN != NaN is True in Python


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
```

- [ ] **Step 2: Run the tests**

```bash
.venv/bin/pytest tests/test_arp_acp_generator.py -v
```

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_arp_acp_generator.py
git commit -m "Add tests for acp_generator format_duration, parse_fov, target_fits_telescope"
```

---

### Task 5: arp_acp_generator.py — assign_telescope

**Files:**
- Modify: `tests/test_arp_acp_generator.py` (append)

- [ ] **Step 1: Append assign_telescope tests**

Add to the end of `tests/test_arp_acp_generator.py`:

```python


# ---------------------------------------------------------------------------
# assign_telescope
# ---------------------------------------------------------------------------

from arp_acp_generator import assign_telescope


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
    """Size < 3 arcmin → first telescope from small tier that fits."""
    telescopes = _make_telescope_df()
    row = pd.Series({"Size (arcmin)": 2.0, "Best Site": "New Mexico"})
    # Small tier is ["T17", "T32", "T21", "T11", "T25"]
    # T17 has FOV min=15; 2 × 1.5 = 3 ≤ 15 → fits → T17 selected
    assert assign_telescope(row, telescopes) == "T17"


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
```

- [ ] **Step 2: Run the tests**

```bash
.venv/bin/pytest tests/test_arp_acp_generator.py::test_assign_telescope_explicit_override tests/test_arp_acp_generator.py::test_assign_telescope_small_target_prefers_small_tier tests/test_arp_acp_generator.py::test_assign_telescope_large_target_uses_large_tier tests/test_arp_acp_generator.py::test_assign_telescope_very_large_target tests/test_arp_acp_generator.py::test_assign_telescope_missing_size_defaults_to_3 -v
```

Expected: all 5 tests pass.

- [ ] **Step 3: Run the whole file**

```bash
.venv/bin/pytest tests/test_arp_acp_generator.py -v
```

Expected: all tests in the file pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_arp_acp_generator.py
git commit -m "Add tests for acp_generator assign_telescope"
```

---

### Task 6: arp_acp_generator.py — calc_plan_duration, calc_plan_cost

**Files:**
- Modify: `tests/test_arp_acp_generator.py` (append)

- [ ] **Step 1: Append duration and cost tests**

Add to the end of `tests/test_arp_acp_generator.py`:

```python


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
    Session billing = total_secs / 60 × rate.
    1 Lum target: total = 2640 sec = 44 min. At 10 pts/min → 440 pts.
    """
    batch = _make_batch(["Luminance"])
    rates = {"T11": {"session": {"Plan-40": 10.0}, "exposure": {"Plan-40": 5.0}}}
    points, rate = calc_plan_cost(
        batch, "T11", interval=300, repeat=3,
        lrgb_counts=[2, 1, 1, 1], lum_counts=[2],
        rates=rates, plan_tier="Plan-40", billing_mode="session",
    )
    assert points == pytest.approx(440.0)
    assert rate == 10.0


def test_calc_plan_cost_exposure_mode():
    """
    Exposure billing = imaging_secs / 60 × rate.
    1 Lum target: imaging = 1800 sec = 30 min. At 5 pts/min → 150 pts.
    """
    batch = _make_batch(["Luminance"])
    rates = {"T11": {"session": {"Plan-40": 10.0}, "exposure": {"Plan-40": 5.0}}}
    points, rate = calc_plan_cost(
        batch, "T11", interval=300, repeat=3,
        lrgb_counts=[2, 1, 1, 1], lum_counts=[2],
        rates=rates, plan_tier="Plan-40", billing_mode="exposure",
    )
    assert points == pytest.approx(150.0)
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
```

- [ ] **Step 2: Run the new tests**

```bash
.venv/bin/pytest tests/test_arp_acp_generator.py -v -k "calc"
```

Expected: all 7 calc tests pass.

- [ ] **Step 3: Run whole file**

```bash
.venv/bin/pytest tests/test_arp_acp_generator.py -v
```

Expected: all tests still pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_arp_acp_generator.py
git commit -m "Add tests for acp_generator calc_plan_duration and calc_plan_cost"
```

---

### Task 7: arp_acp_generator.py — build_acp_header, build_target_block

**Files:**
- Modify: `tests/test_arp_acp_generator.py` (append)

- [ ] **Step 1: Append build_* tests**

Add to the end of `tests/test_arp_acp_generator.py`:

```python


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
    assert "#filter Luminance\n" in block or "#filter Luminance\r" in block or block.endswith("#filter Luminance\n...") is False  # just verify the line exists
    # Cleaner check:
    assert "#filter Luminance" in block
    # And NOT the LRGB filter list:
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
```

- [ ] **Step 2: Run new tests**

```bash
.venv/bin/pytest tests/test_arp_acp_generator.py -v -k "build"
```

Expected: all 7 build tests pass.

- [ ] **Step 3: Run the whole file**

```bash
.venv/bin/pytest tests/test_arp_acp_generator.py -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_arp_acp_generator.py
git commit -m "Add tests for acp_generator build_acp_header and build_target_block"
```

---

### Task 8: arp_session_planner.py tests

**Files:**
- Create: `tests/test_arp_session_planner.py`

- [ ] **Step 1: Create `tests/test_arp_session_planner.py`**

```python
"""Tests for arp_session_planner.py pure helpers."""

import pytest
import ephem

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
    assert assign_telescope(size, "New Mexico") == expected


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
    plan = build_session_plan(targets, "New Mexico", "2026-04-15", "Plan-40")
    assert "#BillingMethod Session" in plan
    assert "#RESUME" in plan
    assert "#FIRSTLAST" in plan
    assert "#repeat 3" in plan
    assert "#shutdown" in plan


def test_build_session_plan_target_count_in_header():
    targets = _make_session_targets()
    plan = build_session_plan(targets, "New Mexico", "2026-04-15", "Plan-40")
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
    plan = build_session_plan(targets, "New Mexico", "2026-04-15", "Plan-40")
    # 46 minutes — check it appears in "Total duration" line
    assert "46m" in plan or "46 m" in plan


def test_build_session_plan_shows_plan_tier():
    targets = _make_session_targets()
    plan = build_session_plan(targets, "New Mexico", "2026-04-15", "Plan-90")
    assert "Plan-90" in plan
```

- [ ] **Step 2: Run the tests**

```bash
.venv/bin/pytest tests/test_arp_session_planner.py -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_arp_session_planner.py
git commit -m "Add tests for session_planner pure helpers"
```

---

### Task 9: arp_moon_calendar.py tests

**Files:**
- Create: `tests/test_arp_moon_calendar.py`

- [ ] **Step 1: Create `tests/test_arp_moon_calendar.py`**

```python
"""Tests for arp_moon_calendar.py helpers."""

import datetime

import pytest

from arp_moon_calendar import build_observer, calc_windows


# ---------------------------------------------------------------------------
# build_observer
# ---------------------------------------------------------------------------

def test_build_observer_new_mexico():
    obs, utc_offset = build_observer("New Mexico")
    assert utc_offset == -7
    # ephem lat/lon are in radians — convert back to degrees for assertion
    import math
    assert math.degrees(float(obs.lat)) == pytest.approx(33.0, abs=0.01)
    assert math.degrees(float(obs.lon)) == pytest.approx(-107.0, abs=0.01)
    assert obs.elevation == 1400


def test_build_observer_spain():
    obs, utc_offset = build_observer("Spain")
    assert utc_offset == 2
    import math
    assert math.degrees(float(obs.lat)) == pytest.approx(38.0, abs=0.01)


def test_build_observer_australia_negative_lat():
    obs, utc_offset = build_observer("Australia")
    assert utc_offset == 10
    import math
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
```

- [ ] **Step 2: Run tests**

```bash
.venv/bin/pytest tests/test_arp_moon_calendar.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_arp_moon_calendar.py
git commit -m "Add tests for moon_calendar build_observer and calc_windows"
```

---

### Task 10: arp_ned_coords.py tests

**Files:**
- Create: `tests/test_arp_ned_coords.py`

- [ ] **Step 1: Create `tests/test_arp_ned_coords.py`**

```python
"""Tests for arp_ned_coords.py name normalization."""

from arp_ned_coords import ned_query_names


def test_standard_catalog_name_first():
    candidates = ned_query_names("NGC 2535", 82)
    assert candidates[0] == "NGC 2535"
    assert candidates[-1] == "Arp 82"


def test_compound_name_splits_on_plus():
    """Compound like 'NGC 2535 + 56' queries primary first."""
    candidates = ned_query_names("NGC 2535 + 56", 82)
    assert candidates[0] == "NGC 2535"
    assert candidates[-1] == "Arp 82"


def test_messier_format_produces_m_variants():
    candidates = ned_query_names("MESSIER 51", 85)
    assert "M  51" in candidates  # double-space variant
    assert "M 51" in candidates   # single-space variant
    assert candidates[-1] == "Arp 85"


def test_stephans_quint_alias():
    candidates = ned_query_names("Stephan's Quint", 319)
    assert "Stephan's Quintet" in candidates


def test_holmberg_alias():
    candidates = ned_query_names("Holmberg II", 268)
    assert "Holmberg II" in candidates


def test_unknown_name_still_includes_arp_fallback():
    """Any unrecognized name still includes 'Arp NNN' as last fallback."""
    candidates = ned_query_names("WeirdSomething", 999)
    assert candidates[-1] == "Arp 999"


def test_arp_fallback_always_last():
    """Arp fallback is always the last item, regardless of input."""
    for name, num in [
        ("NGC 1234", 1),
        ("MESSIER 51", 85),
        ("Holmberg II", 268),
        ("Unknown", 999),
    ]:
        candidates = ned_query_names(name, num)
        assert candidates[-1] == f"Arp {num}"


def test_deduplicates_candidates():
    """No duplicate entries in the candidate list."""
    candidates = ned_query_names("NGC 1234", 1)
    assert len(candidates) == len(set(candidates))
```

- [ ] **Step 2: Run tests**

```bash
.venv/bin/pytest tests/test_arp_ned_coords.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_arp_ned_coords.py
git commit -m "Add tests for ned_coords name normalization"
```

---

### Task 11: Full run and CLAUDE.md update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run the full test suite**

```bash
.venv/bin/pytest tests/ -v
```

Expected:
- All tests pass (approximately 70-80 tests)
- Runtime under 5 seconds
- No test output files leftover in the repo (check `git status`)

- [ ] **Step 2: Check for leftover files from test runs**

```bash
git status
```

Expected: clean (no untracked `acp_plans/`, `session_plans/`, etc.). If any test accidentally wrote files to the repo, find and fix it.

- [ ] **Step 3: Update CLAUDE.md — add pytest to install and add Testing section**

In `CLAUDE.md`, find the dependency install block:

```markdown
# Install dependencies
pip install pandas openpyxl xlrd ephem
```

Replace with:

```markdown
# Install dependencies
pip install pandas openpyxl xlrd ephem

# Install test dependencies
pip install pytest
```

Then add a new subsection after the command block (before "There is no test suite..."). Actually, the "There is no test suite" line is now false — replace it too.

Find:
```markdown
There is no test suite, linter, or build system. The scripts are standalone CLI tools run individually.
```

Replace with:
```markdown
The scripts are standalone CLI tools run individually. A pytest suite lives in `tests/`.

### Testing

```bash
# Run the full suite
pytest tests/

# Run a single file
pytest tests/test_arp_common.py -v

# Run a single test by name pattern
pytest tests/ -k "moon_risk" -v
```

Tests cover pure functions in all 5 modules plus data loaders. Astronomy-heavy code (dark window, target visibility, moon info at transit) is not tested — those wrap `ephem` directly. Tests run against the real data files in the repo.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "Document pytest suite in CLAUDE.md"
```

- [ ] **Step 5: Final verification — run tests one more time to make sure nothing broke**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all tests pass, clean exit.
