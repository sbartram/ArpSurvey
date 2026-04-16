# Design: Extract shared module and fix bugs

**Date:** 2026-04-15
**Status:** Approved
**Approach:** Approach 2 — shared module with constants + utility functions

## Goal

Eliminate duplicated code across the four Python scripts and fix correctness bugs, without changing CLI interfaces, output formats, or the dashboard.

## New file: `arp_common.py`

A single shared module imported by all four scripts. Contains only code that is currently duplicated or logically shared.

### Constants

All of these are currently defined independently in 2-4 scripts. After extraction, each exists in one place.

| Constant | Current locations | Notes |
|---|---|---|
| `DATA_DIR` | all 4 scripts | `Path(__file__).parent` |
| `SEASONAL_PLAN_FILE` | all 4 scripts | |
| `TELESCOPE_FILE` | acp_generator, session_planner | |
| `OBSERVATORIES` | session_planner, moon_calendar | Use session_planner's version (superset, includes `min_el`) |
| `SITE_MAP` | session_planner, moon_calendar | Standardize on list form `{"key": ["Site1", "Site2"]}`. Moon calendar uses `[0]` for primary |
| `TELESCOPE_TIERS` | acp_generator, session_planner | Identical |
| `PLAN_TIERS` | acp_generator, session_planner | Identical |
| `PHASE_THRESHOLDS` | session_planner, moon_calendar | Identical |
| `GOOD_MARGIN` | session_planner, moon_calendar | Identical (20) |
| `SEASON_SHEETS` | acp_generator | Moves to common for consistency |
| `SITE_TELESCOPES` | acp_generator | Moves to common — logically part of site config |
| `LRGB_FILTERS`, `LUM_FILTERS` | acp_generator (in DEFAULTS dict) | `["Luminance", "Red", "Green", "Blue"]` and `["Luminance"]` |
| `LRGB_COUNTS`, `LUM_COUNTS`, `INTERVAL` | session_planner (also as DEFAULTS dict in acp_generator) | Canonical defaults |
| `OVERHEAD_PER_TARGET_SECS`, `OVERHEAD_SESSION_SECS` | acp_generator (session_planner uses inline `180`, `300`) | Named constants replace magic numbers |
| `RISK_LABELS` | new | `{"G": "Good", "M": "Marginal", "A": "Avoid"}` for display |

### Data loading functions

| Function | Signature | Current locations | Notes |
|---|---|---|---|
| `load_targets` | `(sheet_name="All Objects") -> DataFrame` | all 4 scripts | Use acp_generator's parameterized version. Strips column names. |
| `load_telescopes` | `(filepath=TELESCOPE_FILE) -> DataFrame` | acp_generator | |
| `load_rates` | `(filepath=TELESCOPE_FILE) -> dict` | acp_generator, session_planner | Use acp_generator's full version (session + exposure rates). Session planner accesses `rates[tel]["session"]`. |
| `load_ned_coords` | `() -> dict` | acp_generator, session_planner | Identical |

### Coordinate utilities

| Function | Signature | Current locations |
|---|---|---|
| `parse_ra` | `(s: str) -> str` | session_planner, moon_calendar |
| `parse_dec` | `(s: str) -> str` | session_planner, moon_calendar |
| `sanitize_name` | `(name: str) -> str` | acp_generator, session_planner |
| `parse_catalog_coords` | `(ra_str, dec_str) -> (ra_deg, dec_deg)` | ned_coords |

### Moon risk

| Function | Signature | Notes |
|---|---|---|
| `moon_risk` | `(phase: float, separation: float) -> str` | Returns `"G"`, `"M"`, or `"A"`. Standardized from two divergent implementations. |

Session planner uses `RISK_LABELS[code]` to display `"Good"/"Marginal"/"Avoid"` in its output.

## Bug fixes

### Bug 1: Bare `except:` in rate parsing

**File:** `arp_session_planner.py:107`
**Current:** `except: sess_rates[plan] = None`
**Fix:** `except (ValueError, TypeError, IndexError):` — matches the already-correct acp_generator version. After extraction, this code lives in `arp_common.load_rates()` with the correct exception types.

### Bug 2: `--min-el` flag is accepted but ignored

**File:** `arp_session_planner.py:579` (parsed), never applied
**Current:** `args.min_el` is parsed by argparse but the value is never used to override `OBSERVATORIES[obs_key]["min_el"]`.
**Fix:** In session planner's `run()`, after resolving `obs_key`, apply the override:
```python
if args.min_el is not None:
    OBSERVATORIES[obs_key]["min_el"] = args.min_el
```
Since `OBSERVATORIES` is now imported from `arp_common`, we need to make a local copy to avoid mutating the shared dict:
```python
cfg = dict(OBSERVATORIES[obs_key])
if args.min_el is not None:
    cfg["min_el"] = args.min_el
```
Then pass `cfg` instead of looking up `OBSERVATORIES[obs_key]` throughout `run()`.

### Bug 3: Dead code from stale column name

**File:** `arp_acp_generator.py:403`
**Current:** `row[" Dec"]` with a leading space, falling back to `row["Dec (J2000)"]`. The existing `load_targets()` already strips column names (line 170), so the `" Dec"` branch is dead code that never executes — the fallback `"Dec (J2000)"` is always used. Not an active bug, but confusing dead code.
**Fix:** Remove the dead `" Dec"` branch. Standardize on `"Dec (J2000)"` consistently.

### Bug 4: Inconsistent moon risk return values

**Current:** Moon calendar returns `"G"/"M"/"A"`. Session planner returns `"Good"/"Marginal"/"Avoid"`.
**Fix:** Single `moon_risk()` in arp_common returns `"G"/"M"/"A"`. New `RISK_LABELS` dict provides display names. Session planner must update all comparison/filter logic to use short codes:
- `moon_info["risk"] == "Avoid"` becomes `== "A"` (line 483, moon-ok-only filter)
- `t["moon"]["risk"] != "Avoid"` becomes `!= "A"` (line 521)
- `t["moon"]["risk"] == "Marginal"` becomes `== "M"` (line 522)
- `t["moon"]["risk"] == "Avoid"` becomes `== "A"` (line 523)
- `t["moon"]["risk"] == "Good"` / `"Marginal"` becomes `== "G"` / `"M"` (line 526)

Use `RISK_LABELS[code]` only for display output (table printing and ACP plan comments).

## Changes per script

### `arp_acp_generator.py`

- **Remove:** ~60 lines — all constants listed above, `load_telescopes()`, `load_rates()`, `load_targets()`, `load_ned_coords()`, `sanitize_name()`, the `DEFAULTS` dict
- **Add:** `from arp_common import ...` (including `SITE_TELESCOPES`, `LRGB_FILTERS`, `LUM_FILTERS`, `SEASON_SHEETS`)
- **Keep as-is:** `assign_telescope()`, `target_fits_telescope()`, `parse_fov()`, `build_acp_header()`, `generate_plan_text()`, `calc_plan_duration()`, `calc_plan_cost()`, `format_duration()`, `run()`, CLI
- **Adjust:** `build_target_block()` must replace `DEFAULTS["lrgb_filters"]` with `LRGB_FILTERS` and `DEFAULTS["lum_filters"][0]` with `LUM_FILTERS[0]` (lines 409, 414)
- **Note:** `parse_fov()` and `target_fits_telescope()` stay local — only used by this script's `assign_telescope()`
- **Note:** The `DEFAULTS` dict is fully replaced by importing the canonical constants directly (`LRGB_FILTERS`, `LUM_FILTERS`, `LRGB_COUNTS`, `LUM_COUNTS`, `INTERVAL`)
- **Adjust:** `run()` must map `args.season` through `SEASON_SHEETS` before calling `load_targets(sheet_name=...)`, since `load_targets()` no longer accepts a season key

### `arp_session_planner.py`

- **Remove:** ~70 lines — constants, `load_targets()`, `load_rates()`, `load_ned_coords()`, `parse_ra()`, `parse_dec()`, `sanitize_name()`, `moon_risk()`
- **Add:** `from arp_common import ...`
- **Keep as-is:** `get_dark_window()`, `get_target_visibility()`, `get_moon_info()`, `assign_telescope()`, `run()`, CLI
- **Fix:** `--min-el` override applied, bare `except` corrected, `moon_risk()` uses common version + `RISK_LABELS`
- **Adjust:** `estimate_cost()` (line 300) and `build_session_plan()` (line 329) must replace hardcoded `180` and `300` with `OVERHEAD_PER_TARGET_SECS` and `OVERHEAD_SESSION_SECS`
- **Adjust:** All moon risk comparison logic must switch from `"Good"/"Marginal"/"Avoid"` to `"G"/"M"/"A"` short codes (see Bug 4 for full list of affected lines)
- **Note:** `load_rates()` now returns the full structure; all rate consumers must change access pattern from `rates[tel][plan_tier]` to `rates[tel]["session"][plan_tier]`. This affects the `rates.get(tel, {}).get(plan_tier)` call in `run()` (line 487); `estimate_cost()` receives the already-extracted rate scalar and does not need dict access changes.

### `arp_moon_calendar.py`

- **Remove:** ~40 lines — `OBSERVATORIES`, `SITE_MAP`, `PHASE_THRESHOLDS`, `GOOD_MARGIN`, `load_targets()`, `parse_ra()`, `parse_dec()`, `moon_risk()`
- **Add:** `from arp_common import ...`
- **Keep as-is:** `build_observer()`, `calc_windows()`, `run()`, CLI
- **Adjust:** `SITE_MAP` access changes from `SITE_MAP.get(site_str, "New Mexico")` to `SITE_MAP.get(site_str, ["New Mexico"])[0]`

### `arp_ned_coords.py`

- **Remove:** ~15 lines — `load_targets()`, `parse_catalog_coords()`
- **Add:** `from arp_common import ...`
- **Keep as-is:** `ned_query_names()`, `query_ned()`, `run()`, CLI

## What does NOT change

- CLI interface of every script (arguments, invocation style)
- Output file formats (ACP plans, CSVs, JSON)
- Output file naming conventions
- `arp_project.html` dashboard
- Any data files (`.xlsx`, `.csv`, `.tsv`, `.json`)
- The `update_coords.sh` script

## Risk mitigation

- Each script retains its own `run()` and CLI — no change to how they are invoked
- The shared module contains only pure functions and constants — no global state, no side effects on import
- `DATA_DIR` in arp_common uses `Path(__file__).parent`, which resolves correctly as long as `arp_common.py` lives alongside the other scripts (same directory as today)

## Validation

After implementation, verify by running each script and confirming output matches pre-refactoring behavior:

1. `python arp_acp_generator.py --season Spring` — diff generated plan files and summary CSV against pre-refactoring output
2. `python arp_session_planner.py --site "New Mexico"` — diff ACP plan and JSON summary against pre-refactoring output
3. `python arp_moon_calendar.py --days 7` — diff JSON output against pre-refactoring output (use short window for speed)
4. `python arp_ned_coords.py --help` — verify CLI still parses (full run requires network, so just check import + help)
5. Verify `--min-el` fix: `python arp_session_planner.py --min-el 45` should produce fewer targets than default `--min-el 30`
