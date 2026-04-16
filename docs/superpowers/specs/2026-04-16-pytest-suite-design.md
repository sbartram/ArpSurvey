# Design: pytest test suite (level B — unit + data loaders)

**Date:** 2026-04-16
**Status:** Approved
**Scope:** Unit tests for pure functions + tests for data loaders. Astronomy-heavy and CLI-level code is out of scope.

## Goal

Add a pytest-based test suite that covers:
- Pure functions in all 5 Python modules
- Data loaders (`load_targets`, `load_telescopes`, `load_rates`, `load_ned_coords`)
- Regression guards for the 4 bugs fixed in the prior refactor (bare except, `--min-el`, dead Dec code, inconsistent moon risk codes)

Out of scope: astronomy functions (`get_dark_window`, `get_target_visibility`, `get_moon_info`, `calc_windows`), CLI `run()` entry points, network-dependent NED queries.

## Structure

```
tests/
├── __init__.py                   # empty, marks package
├── test_arp_common.py
├── test_arp_acp_generator.py
├── test_arp_session_planner.py
├── test_arp_moon_calendar.py
└── test_arp_ned_coords.py
```

- One test file per source module.
- Tests run from the repo root: `.venv/bin/pytest tests/`.
- `pyproject.toml` at repo root sets `testpaths = ["tests"]` and `pythonpath = ["."]` so `import arp_common` works from any test file.
- Tests use real data files (`Arp_Seasonal_Plan.xlsx`, `itelescopesystems.xlsx`, `arp_ned_coords.csv`) for loader tests — no separate fixture Excel files.
- Pure-function tests use inline `@pytest.mark.parametrize` cases, no data file dependency.

## Dependencies

Add `pytest` to install instructions. No other dev dependencies required (no pytest-cov, no mock library — pytest's built-in `monkeypatch` is enough for the single filesystem-absence test case).

## Test specifications

### `tests/test_arp_common.py`

**Pure functions — inline parametrized:**

| Test | Input | Expected |
|---|---|---|
| `test_moon_risk_good_phase_bin_1` | phase=10, sep=45 | `"G"` (phase<25, min=20, margin=25≥20) |
| `test_moon_risk_marginal_phase_bin_1` | phase=10, sep=25 | `"M"` (margin=5, 0≤5<20) |
| `test_moon_risk_avoid_phase_bin_1` | phase=10, sep=15 | `"A"` (margin=-5, <0) |
| `test_moon_risk_phase_bin_2_boundary` | phase=24.9, sep=20 | `"M"` (still in <25 bin) |
| `test_moon_risk_phase_bin_2_at_threshold` | phase=25, sep=40 | `"M"` (now in <50 bin, min=40, margin=0) |
| `test_moon_risk_phase_bin_3` | phase=60, sep=85 | `"G"` (in <75 bin, min=60, margin=25≥20) |
| `test_moon_risk_phase_bin_4_full_moon` | phase=100, sep=100 | `"M"` (in <101 bin, min=90, margin=10) |
| `test_moon_risk_phase_bin_4_too_close` | phase=100, sep=60 | `"A"` |
| `test_parse_ra_space_separated` | `"12 34 56"` | `"12:34:56"` |
| `test_parse_ra_colon_separated_idempotent` | `"12:34:56"` | `"12:34:56"` |
| `test_parse_ra_with_whitespace` | `"  12 34 56  "` | `"12:34:56"` |
| `test_parse_dec_positive_fractional_minutes` | `"+45 30.5"` | `"+45:30:30"` |
| `test_parse_dec_negative` | `"-12 15.0"` | `"-12:15:00"` |
| `test_parse_dec_no_sign_defaults_positive` | `"45 30.5"` | `"+45:30:30"` |
| `test_parse_dec_three_parts_returns_unchanged` | `"+45 30 15"` | `"+45 30 15"` (function only handles 2-part input) |
| `test_sanitize_name_spaces_to_underscores` | `"NGC 1234"` | `"NGC_1234"` |
| `test_sanitize_name_preserves_plus` | `"NGC 2535 + 56"` | `"NGC_2535_+_56"` |
| `test_sanitize_name_collapses_multiple_underscores` | `"a   b"` | `"a_b"` |
| `test_sanitize_name_strips_edge_underscores` | `"_foo_"` | `"foo"` |
| `test_sanitize_name_special_chars` | `"Stephan's Quint"` | `"Stephan_s_Quint"` |
| `test_parse_catalog_coords_positive` | `("12 34 56", "+45 30")` | `(188.733333, 45.5)` with `pytest.approx` |
| `test_parse_catalog_coords_negative` | `("03 15 00", "-25 00")` | `(48.75, -25.0)` |
| `test_parse_catalog_coords_two_part_ra` | `("12 34", "+45 30")` | `(188.5, 45.5)` |

**Regression guards:**

| Test | Assertion |
|---|---|
| `test_moon_risk_returns_short_codes` | `moon_risk(50, 80)` returns exactly `"G"` (not `"Good"`). Guards against Bug 4 regression |
| `test_risk_labels_complete` | `RISK_LABELS == {"G": "Good", "M": "Marginal", "A": "Avoid"}` |

**Data loaders:**

| Test | Assertion |
|---|---|
| `test_load_targets_default_sheet` | Returns `pandas.DataFrame`, `len(df) > 300` (338 expected), required columns present, column names stripped |
| `test_load_targets_specific_sheet` | `load_targets("Spring (Now)")` returns smaller DataFrame (<250 rows) |
| `test_load_targets_missing_sheet_raises` | `load_targets("Nonexistent Sheet")` raises exception (either `ValueError` from missing header or `XLRDError`/pandas from missing sheet — accept either) |
| `test_load_telescopes_returns_indexed_df` | `"T11"` is in the index, `"FOV X (arcmins)"` column present |
| `test_load_rates_structure` | Returns dict, every value is `{"session": dict, "exposure": dict}`, each inner dict contains all 5 plan tiers as keys |
| `test_load_rates_values_are_floats_or_none` | For each telescope, every rate is `float` or `None` (no raw pandas NaN leaking through, no exceptions raised) |
| `test_load_ned_coords_present` | Returns dict with >300 entries when `arp_ned_coords.csv` exists |
| `test_load_ned_coords_missing_file` | Use `monkeypatch` to replace `DATA_DIR` with a tmp path → returns `{}` |

### `tests/test_arp_acp_generator.py`

| Test | Input → Expected |
|---|---|
| `test_format_duration_zero` | 0 → `"0m"` |
| `test_format_duration_seconds_only` | 90 → `"1m"` |
| `test_format_duration_exact_hour` | 3600 → `"1h 00m"` |
| `test_format_duration_hours_and_minutes` | 5430 → `"1h 30m"` |
| `test_parse_fov_valid_numeric` | Series with FOV X=30.0, FOV Y=20.0 → `(30.0, 20.0)` |
| `test_parse_fov_missing` | Series with `NaN` → `(None, None)` |
| `test_parse_fov_string_marker` | Series with `"?"` → `(None, None)` |
| `test_target_fits_telescope_fits` | size=10, fov=(30, 20) → True (10 × 1.5 = 15 ≤ 20) |
| `test_target_fits_telescope_just_too_large` | size=14, fov=(20, 20) → False (14 × 1.5 = 21 > 20) |
| `test_target_fits_telescope_none_fov` | size=5, fov=(None, None) → False |
| `test_assign_telescope_explicit_override` | `preferred_telescope="T11"` with T11 in index → returns `"T11"` |
| `test_assign_telescope_small_target` | row with size=2.0, site="New Mexico", mock DataFrame with T17/T11/T21 → returns small-tier pick that fits |
| `test_assign_telescope_large_target` | row with size=10.0, site="New Mexico" → returns large-tier pick |
| `test_assign_telescope_fallback_when_nothing_fits` | size=100 arcmin, no telescopes fit → returns first candidate in tier |
| `test_calc_plan_duration_luminance_only` | 1 Lum target, interval=300, repeat=3, lum_counts=[2] → expected `(total, imaging)` tuple with exact numbers |
| `test_calc_plan_duration_lrgb` | 1 LRGB target, interval=300, repeat=3, lrgb_counts=[2,1,1,1] → expected tuple |
| `test_calc_plan_duration_mixed_batch` | 2 LRGB + 1 Lum → expected totals |
| `test_calc_plan_cost_session_mode` | batch, rates mock with 10 pts/min → expected points (verify math) |
| `test_calc_plan_cost_free_telescope` | rates dict with rate=0 → returns `(0.0, 0.0)` |
| `test_calc_plan_cost_missing_telescope` | tel_id not in rates → `(None, None)` |
| `test_build_acp_header_includes_plan_name` | header string contains "Arp_Spring_T11_batch01" and "; Telescope    : T11" |
| `test_build_acp_header_free_cost` | session_cost=0.0 produces "FREE" in output |
| `test_build_acp_header_no_plan_tier` | plan_tier=None → no "Est. Cost" block |
| `test_build_target_block_lrgb` | LRGB row → output contains `#filter Luminance,Red,Green,Blue` and `#binning 1,2,2,2` |
| `test_build_target_block_luminance` | Lum row → output contains `#filter Luminance` and `#binning 1` |
| `test_build_target_block_uses_ned_coords_when_available` | ned_coords dict provided with arp=82 → output uses those RA/Dec, not parsed catalog |

### `tests/test_arp_session_planner.py`

| Test | Input → Expected |
|---|---|
| `test_ephem_to_local` | Known ephem float + utc_offset → expected "HH:MM" string |
| `test_estimate_cost_lrgb` | strategy="LRGB", rate_per_min=10 → deterministic integer |
| `test_estimate_cost_luminance` | strategy="Luminance", rate_per_min=10 → smaller than LRGB cost |
| `test_estimate_cost_none_rate` | rate_per_min=None → None |
| `test_assign_telescope_small` | size=2.0 → `"T17"` |
| `test_assign_telescope_medium` | size=5.0 → `"T11"` |
| `test_assign_telescope_large` | size=10.0 → `"T5"` |
| `test_assign_telescope_very_large` | size=25.0 → `"T14"` |
| `test_build_session_plan_contains_required_directives` | call with 2 targets → returns string containing `#BillingMethod Session`, `#RESUME`, `#FIRSTLAST`, `#repeat 3`, `#shutdown` |
| `test_build_session_plan_target_count_in_header` | plan text contains `"Targets     : 2"` |
| `test_build_session_plan_uses_named_overhead_constants` | with 3 targets, the "Total duration" line matches `3 × OVERHEAD_PER_TARGET_SECS + OVERHEAD_SESSION_SECS + imaging` — guards against the magic-number regression |

### `tests/test_arp_moon_calendar.py`

| Test | Input → Expected |
|---|---|
| `test_build_observer_new_mexico` | Returns `(observer, -7)`; observer.lat ≈ 33°, lon ≈ -107° |
| `test_build_observer_spain` | Returns `(observer, 2)`; observer.lat ≈ 38° |
| `test_build_observer_australia` | Returns `(observer, 10)`; observer.lat ≈ -31.3° |
| `test_calc_windows_structure` | 3-day window → list of 3 dicts, each has keys `{"d", "p", "s", "r"}`; every `r` value in `{"G", "M", "A"}` |
| `test_calc_windows_date_sequence` | 5-day window starting 2026-05-01 → dates are 2026-05-01..2026-05-05 consecutively |

### `tests/test_arp_ned_coords.py`

| Test | Input → Expected |
|---|---|
| `test_ned_query_names_standard_catalog` | `("NGC 2535", 82)` → first candidate is `"NGC 2535"`, last is `"Arp 82"` |
| `test_ned_query_names_compound` | `("NGC 2535 + 56", 82)` → primary name `"NGC 2535"` first, last is `"Arp 82"` |
| `test_ned_query_names_messier` | `("MESSIER 51", 85)` → list contains `"M  51"` (double space) and `"M 51"` (single space) |
| `test_ned_query_names_stephans_quint` | `("Stephan's Quint", 319)` → list contains `"Stephan's Quintet"` alias |
| `test_ned_query_names_holmberg` | `("Holmberg II", 268)` → list contains `"Holmberg II"` alias |
| `test_ned_query_names_fallback_arp_always_last` | Any input → last element is always `f"Arp {num}"` |
| `test_ned_query_names_deduplicates` | Input that would produce duplicate candidates → result has no duplicates |
| `test_ned_query_names_unknown_name` | `("WeirdName", 999)` → returns at least primary + `"Arp 999"`, no crash |

## Configuration files

### `pyproject.toml` (new, at repo root)

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

This is the minimum needed. It lets tests run with a plain `pytest` invocation from the repo root, without needing `sys.path` manipulation in each test file.

### `tests/__init__.py` (new, empty)

Marks `tests/` as a package so pytest can discover it cleanly.

## CLAUDE.md updates

- Add `pip install pytest` to install instructions
- Add a "Testing" subsection under "Commands" with `pytest tests/` and a note about the test file layout
- Under "Architecture", add a one-line note: "Test suite lives in `tests/` with one test file per source module"

## What does NOT change

- No source code changes (except possibly minor import adjustments if a function is currently nested inside `run()` and needs to be moved to module scope to be testable; none identified so far)
- No CLI changes to any script
- No output format changes
- No new runtime dependencies (pytest is dev-only)

## Validation

- `.venv/bin/pytest tests/ -v` runs all tests, all pass
- Tests complete in under 5 seconds
- `pytest tests/test_arp_common.py::test_moon_risk_marginal_phase_bin_1 -v` runs a single test
- Running tests does NOT produce output files in the repo (no leftover `acp_plans/` or `session_plans/` from test runs — any test that calls a function writing files must write to `tmp_path` from pytest)
