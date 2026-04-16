# Shared Module Extraction & Bug Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract duplicated constants and utility functions from four Python scripts into a shared `arp_common.py` module, and fix four correctness/cleanliness bugs.

**Architecture:** Create `arp_common.py` alongside the existing scripts (same directory). Each script replaces its local constants and duplicated functions with imports from the shared module. Scripts retain their own `run()`, CLI, and domain-specific logic. No changes to CLI interfaces or output formats.

**Tech Stack:** Python 3.9+, pandas, ephem

**Spec:** `docs/superpowers/specs/2026-04-15-shared-module-and-bug-fixes-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| **Create** | `arp_common.py` | All shared constants, data loaders, coordinate utils, moon risk |
| **Modify** | `arp_acp_generator.py` | Remove ~60 lines of duplicated code, import from common |
| **Modify** | `arp_session_planner.py` | Remove ~70 lines, import from common, fix 3 bugs |
| **Modify** | `arp_moon_calendar.py` | Remove ~40 lines, import from common |
| **Modify** | `arp_ned_coords.py` | Remove ~15 lines, import from common |

---

### Task 1: Capture baseline outputs for validation

Before any code changes, generate reference outputs from all scripts to diff against after refactoring.

**Files:**
- Read: `arp_acp_generator.py`, `arp_session_planner.py`, `arp_moon_calendar.py`

- [ ] **Step 1: Generate baseline ACP plans**

```bash
python arp_acp_generator.py --season Spring --output-dir /tmp/arp_baseline/acp_plans
```

- [ ] **Step 2: Generate baseline session plan**

```bash
python arp_session_planner.py --site "New Mexico" --output-dir /tmp/arp_baseline/session_plans
```

- [ ] **Step 3: Generate baseline moon calendar (short window)**

```bash
python arp_moon_calendar.py --days 7 --output /tmp/arp_baseline/moon_data.json
```

- [ ] **Step 4: Verify NED coords script imports cleanly**

```bash
python -c "import arp_ned_coords; print('OK')"
```

- [ ] **Step 5: Commit — no code changes, just record that baseline was captured**

No commit needed — these are ephemeral reference files.

---

### Task 2: Create `arp_common.py` with constants

**Files:**
- Create: `arp_common.py`

- [ ] **Step 1: Create `arp_common.py` with all shared constants**

```python
#!/usr/bin/env python3
"""
Shared constants and utilities for the Arp catalog iTelescope toolkit.

Imported by: arp_acp_generator.py, arp_session_planner.py,
             arp_moon_calendar.py, arp_ned_coords.py
"""

import re
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent
SEASONAL_PLAN_FILE = DATA_DIR / "Arp_Seasonal_Plan.xlsx"
TELESCOPE_FILE = DATA_DIR / "itelescopesystems.xlsx"

# ---------------------------------------------------------------------------
# Observatory configuration
# ---------------------------------------------------------------------------

OBSERVATORIES = {
    "New Mexico": {"lat": "33.0",  "lon": "-107.0", "elev": 1400, "utc_offset": -7,  "min_el": 30},
    "Spain":      {"lat": "38.0",  "lon": "-3.5",   "elev": 1200, "utc_offset":  2,  "min_el": 30},
    "Australia":  {"lat": "-31.3", "lon": "149.1",  "elev": 1100, "utc_offset": 10,  "min_el": 30},
    "Chile":      {"lat": "-30.0", "lon": "-70.7",  "elev": 1500, "utc_offset": -4,  "min_el": 30},
}

# Map "Best Site" column values to list of compatible observatory keys.
# Use [0] for the primary site (e.g. for moon calendar which needs one site).
SITE_MAP = {
    "New Mexico / Spain":     ["New Mexico", "Spain"],
    "New Mexico / Australia": ["New Mexico", "Australia"],
    "Any site":               ["New Mexico", "Spain", "Chile", "Australia"],
    "Australia":              ["Australia"],
    "New Mexico":             ["New Mexico"],
    "Spain":                  ["Spain"],
    "Chile":                  ["Chile"],
}

# Site-to-telescope mapping for auto-assignment
SITE_TELESCOPES = {
    "New Mexico": ["T5", "T8", "T14", "T11", "T21", "T25", "T68"],
    "Spain":      ["T17", "T20", "T30", "T32", "T33", "T59"],
    "Australia":  ["T24", "T18"],
    "Chile":      ["T71", "T72", "T73", "T74", "T75"],
}

# ---------------------------------------------------------------------------
# Telescope and plan configuration
# ---------------------------------------------------------------------------

# Telescope preference order for auto-assignment based on target angular size.
# Format: (min_arcmin, max_arcmin, preferred_telescope_ids_in_order)
TELESCOPE_TIERS = [
    (0,    3.0,  ["T17", "T32", "T21", "T11", "T25"]),   # compact targets
    (3.0,  7.0,  ["T11", "T21", "T26", "T30", "T17"]),   # medium targets
    (7.0,  20.0, ["T5",  "T20", "T26", "T71", "T75"]),   # large targets
    (20.0, 999,  ["T14", "T8",  "T70", "T80"]),           # very wide targets
]

# iTelescope membership plan tiers (column names in Imaging Rates sheet)
PLAN_TIERS = ["Plan-40", "Plan-90", "Plan-160", "Plan-290", "Plan-490"]

# Season name → Excel sheet name mapping
SEASON_SHEETS = {
    "Spring":  "Spring (Now)",
    "Summer":  "Summer",
    "Autumn":  "Autumn",
    "Winter":  "Winter",
    "All":     "All Objects",
}

# ---------------------------------------------------------------------------
# Imaging defaults
# ---------------------------------------------------------------------------

LRGB_FILTERS = ["Luminance", "Red", "Green", "Blue"]
LUM_FILTERS = ["Luminance"]

LRGB_COUNTS = [2, 1, 1, 1]   # per-repeat filter counts for LRGB
LUM_COUNTS = [2]              # per-repeat filter counts for Luminance-only
INTERVAL = 300                # seconds per sub-exposure

# Per-target overhead estimate in seconds (slew + plate-solve + focus + guider settle)
OVERHEAD_PER_TARGET_SECS = 180

# ACP startup overhead per plan session in seconds (roof open, startup, first slew)
OVERHEAD_SESSION_SECS = 300

# ---------------------------------------------------------------------------
# Moon risk classification
# ---------------------------------------------------------------------------

# Moon phase (%) → minimum separation (degrees) thresholds
PHASE_THRESHOLDS = [
    (25,  20),   # phase < 25%  → 20 deg min
    (50,  40),   # phase < 50%  → 40 deg min
    (75,  60),   # phase < 75%  → 60 deg min
    (101, 90),   # phase < 101% → 90 deg min
]

GOOD_MARGIN = 20  # degrees above minimum to qualify as "Good"

RISK_LABELS = {"G": "Good", "M": "Marginal", "A": "Avoid"}


def moon_risk(phase, separation):
    """Return 'G' (good), 'M' (marginal), or 'A' (avoid)."""
    min_sep = next(m for p, m in PHASE_THRESHOLDS if phase < p)
    margin = separation - min_sep
    if margin >= GOOD_MARGIN:
        return "G"
    elif margin >= 0:
        return "M"
    return "A"
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
python -c "from arp_common import *; print('OK')"
```

Expected: `OK` with no errors.

- [ ] **Step 3: Commit**

```bash
git add arp_common.py
git commit -m "Add arp_common.py with shared constants and moon_risk()"
```

---

### Task 3: Add data loading and coordinate utility functions to `arp_common.py`

**Files:**
- Modify: `arp_common.py`

- [ ] **Step 1: Add data loading functions to `arp_common.py`**

Append after the `moon_risk` function:

```python
# ---------------------------------------------------------------------------
# Coordinate utilities
# ---------------------------------------------------------------------------

def parse_ra(s):
    """Convert 'HH MM SS' to 'HH:MM:SS' for ephem."""
    s = str(s).strip()
    return s.replace(" ", ":") if " " in s else s


def parse_dec(s):
    """Convert '+DD MM.m' to '+DD:MM:SS' for ephem."""
    s = str(s).strip()
    sign = "-" if s.startswith("-") else "+"
    body = s.lstrip("+-")
    parts = body.split()
    if len(parts) == 2:
        deg = parts[0]
        min_decimal = float(parts[1])
        mins = int(min_decimal)
        secs = int((min_decimal - mins) * 60)
        return f"{sign}{deg}:{mins:02d}:{secs:02d}"
    return s


def sanitize_name(name):
    """Make a target name safe for ACP (no spaces, special chars)."""
    name = str(name).strip()
    name = re.sub(r"[^\w\-+]", "_", name)
    name = re.sub(r"_+", "_", name)
    return name.strip("_")


def parse_catalog_coords(ra_str, dec_str):
    """Parse catalog RA/Dec strings to (ra_degrees, dec_degrees)."""
    ra_parts = str(ra_str).strip().split()
    ra_h = float(ra_parts[0]) + float(ra_parts[1]) / 60 + (float(ra_parts[2]) if len(ra_parts) > 2 else 0) / 3600

    dec_str = str(dec_str).strip()
    sign = -1 if dec_str.startswith('-') else 1
    dec_parts = dec_str.lstrip('+-').split()
    dec_d = sign * (float(dec_parts[0]) + float(dec_parts[1]) / 60)

    return ra_h * 15, dec_d


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_targets(sheet_name="All Objects"):
    """
    Load Arp targets from the seasonal plan workbook.
    Returns a DataFrame with stripped column names.
    """
    df = pd.read_excel(SEASONAL_PLAN_FILE, sheet_name=sheet_name, header=None)

    header_row = None
    for i, row in df.iterrows():
        if "Arp #" in row.values or any(str(v) == "Arp #" for v in row.values):
            header_row = i
            break
    if header_row is None:
        raise ValueError(f"Could not find header row in sheet '{sheet_name}'")

    df.columns = df.iloc[header_row]
    df = df.iloc[header_row + 1:].reset_index(drop=True)
    df = df.dropna(subset=["Arp #"])
    df.columns = [str(c).strip() for c in df.columns]
    return df


def load_telescopes(filepath=None):
    """Load telescope specs, return DataFrame keyed by telescope ID."""
    filepath = filepath or TELESCOPE_FILE
    df = pd.read_excel(filepath, sheet_name="Telescopes")
    tels = df[df["Telescope"].notna() & df["Telescope"].astype(str).str.match(r"T\d+")].copy()
    tels = tels.set_index("Telescope")
    return tels


def load_rates(filepath=None):
    """
    Load iTelescope imaging rates from the Imaging Rates sheet.
    Returns a dict: {telescope_id: {"session": {plan: pts}, "exposure": {plan: pts}}}
    Rates are in iTelescope points per minute.
    """
    filepath = filepath or TELESCOPE_FILE
    df = pd.read_excel(filepath, sheet_name="Imaging Rates", header=None)

    header_row = None
    for i, row in df.iterrows():
        if any(str(v).strip() == "Telescope" for v in row.values):
            header_row = i
            break
    if header_row is None:
        return {}

    rates = {}
    for i in range(header_row + 1, len(df)):
        row = df.iloc[i]
        tel_id = str(row.iloc[0]).strip()
        if not tel_id or tel_id == "nan" or not tel_id.startswith("T"):
            continue
        values = list(row.values)
        session_rates = {}
        exposure_rates = {}
        for j, plan in enumerate(PLAN_TIERS):
            try:
                session_rates[plan] = float(values[j + 1])
            except (ValueError, TypeError, IndexError):
                session_rates[plan] = None
            try:
                exposure_rates[plan] = float(values[j + 7])
            except (ValueError, TypeError, IndexError):
                exposure_rates[plan] = None
        rates[tel_id] = {"session": session_rates, "exposure": exposure_rates}
    return rates


def load_ned_coords():
    """
    Load NED-fetched coordinates from arp_ned_coords.csv if it exists.
    Returns dict keyed by Arp number: {arp: (ra_hours, dec_deg)}.
    Falls back to empty dict if file not found.
    """
    ned_path = DATA_DIR / "arp_ned_coords.csv"
    if not ned_path.exists():
        return {}
    try:
        df = pd.read_csv(ned_path)
        coords = {}
        for _, row in df.iterrows():
            if row.get('source') == 'NED':
                coords[int(row['arp'])] = (float(row['ra_hours']), float(row['dec_deg']))
        return coords
    except Exception:
        return {}
```

- [ ] **Step 2: Verify all functions import and work**

```bash
python -c "
from arp_common import load_targets, load_telescopes, load_rates, load_ned_coords
from arp_common import parse_ra, parse_dec, sanitize_name, parse_catalog_coords
df = load_targets()
print(f'Targets: {len(df)}')
tels = load_telescopes()
print(f'Telescopes: {len(tels)}')
rates = load_rates()
print(f'Rates: {len(rates)} telescopes')
ned = load_ned_coords()
print(f'NED coords: {len(ned)}')
print(f'parse_ra: {parse_ra(\"12 34 56\")}')
print(f'parse_dec: {parse_dec(\"+45 30.5\")}')
print(f'sanitize: {sanitize_name(\"NGC 1234 + 56\")}')
print('OK')
"
```

Expected: Target count ~338, telescope count ~24, rate count >0, NED coords >0, parsed strings correct.

- [ ] **Step 3: Commit**

```bash
git add arp_common.py
git commit -m "Add data loaders and coordinate utilities to arp_common"
```

---

### Task 4: Migrate `arp_moon_calendar.py` to use `arp_common`

This is the simplest script to migrate — good to do first to validate the pattern.

**Files:**
- Modify: `arp_moon_calendar.py`

- [ ] **Step 1: Replace imports and remove duplicated code**

Replace lines 1-102 (everything before `build_observer`) with:

```python
#!/usr/bin/env python3
"""
Arp Catalog Moon Avoidance Calendar Generator
==============================================
Calculates moon phase, separation, and imaging risk for every Arp target
over a configurable window, and outputs a JSON file for use in the dashboard.

Usage:
    python arp_moon_calendar.py [--days N] [--output FILE]

Examples:
    python arp_moon_calendar.py --days 90
    python arp_moon_calendar.py --days 60 --output moon_data.json
"""

import argparse
import datetime
import json
import math
import sys

import ephem

from arp_common import (
    OBSERVATORIES, SITE_MAP, load_targets, moon_risk, parse_ra, parse_dec,
)
```

- [ ] **Step 2: Update `build_observer` to use imported `OBSERVATORIES`**

`build_observer` (currently line 105-111) already accesses `OBSERVATORIES` by key — no change needed to its body. It now uses the imported constant which includes `min_el` (extra key is harmless).

- [ ] **Step 3: Update SITE_MAP access in `run()`**

Find this line in `run()`:

```python
        obs_key  = SITE_MAP.get(site_str, "New Mexico")
```

Replace with:

```python
        obs_key  = SITE_MAP.get(site_str, ["New Mexico"])[0]
```

- [ ] **Step 4: Verify output matches baseline**

```bash
python arp_moon_calendar.py --days 7 --output /tmp/arp_test/moon_data.json
diff /tmp/arp_baseline/moon_data.json /tmp/arp_test/moon_data.json
```

Expected: No diff (identical JSON output).

- [ ] **Step 5: Commit**

```bash
git add arp_moon_calendar.py
git commit -m "Migrate arp_moon_calendar.py to use arp_common"
```

---

### Task 5: Migrate `arp_ned_coords.py` to use `arp_common`

**Files:**
- Modify: `arp_ned_coords.py`

- [ ] **Step 1: Replace imports and remove duplicated code**

Replace lines 43-44 (the `DATA_DIR` and `SEASONAL_PLAN_FILE` definitions) with an import. Also remove `load_targets()` (lines 147-156) and `parse_catalog_coords()` (lines 159-170).

The new import section (after the astroquery try/except block, replacing lines 43-44):

```python
from arp_common import SEASONAL_PLAN_FILE, load_targets, parse_catalog_coords
```

Remove the `DATA_DIR` line (line 43), the `SEASONAL_PLAN_FILE` line (line 44), the `load_targets()` function (lines 147-156), and the `parse_catalog_coords()` function (lines 159-170).

- [ ] **Step 2: Verify CLI still works**

```bash
python arp_ned_coords.py --help
```

Expected: Help text prints without import errors.

- [ ] **Step 3: Commit**

```bash
git add arp_ned_coords.py
git commit -m "Migrate arp_ned_coords.py to use arp_common"
```

---

### Task 6: Migrate `arp_acp_generator.py` to use `arp_common`

**Files:**
- Modify: `arp_acp_generator.py`

- [ ] **Step 1: Replace imports and constants**

Replace lines 32-93 (imports through `OVERHEAD_SESSION_SECS`) with:

```python
import argparse
import re
import sys

import pandas as pd
from pathlib import Path

from arp_common import (
    DATA_DIR, SEASONAL_PLAN_FILE, TELESCOPE_FILE,
    TELESCOPE_TIERS, SITE_TELESCOPES, PLAN_TIERS, SEASON_SHEETS,
    LRGB_FILTERS, LUM_FILTERS, LRGB_COUNTS, LUM_COUNTS, INTERVAL,
    OVERHEAD_PER_TARGET_SECS, OVERHEAD_SESSION_SECS,
    load_telescopes, load_rates, load_targets, load_ned_coords, sanitize_name,
)
```

- [ ] **Step 2: Remove the local `DEFAULTS` dict, `load_telescopes()`, `load_rates()`, `load_targets()`, `load_ned_coords()`, and `sanitize_name()` functions**

Delete:
- Lines 66-75: the `DEFAULTS` dict
- Lines 99-104: `load_telescopes()`
- Lines 107-147: `load_rates()`
- Lines 150-171: `load_targets()`
- Lines 178-195: `load_ned_coords()`
- Lines 269-274: `sanitize_name()`

Also remove `import os` (line 33) — it's unused.

- [ ] **Step 3: Update `build_target_block()` to use imported constants**

In `build_target_block()`, replace the DEFAULTS references and dead code:

Replace:

```python
    if ned_coords and arp_int in ned_coords:
        ra_dec, dec_dec = ned_coords[arp_int]
    else:
        ra_str = str(row["RA (J2000)"]).strip().split()
        ra_dec = float(ra_str[0]) + float(ra_str[1])/60 + (float(ra_str[2]) if len(ra_str)>2 else 0)/3600
        dec_str = str(row[" Dec"]).strip() if " Dec" in row.index else str(row["Dec (J2000)"]).strip()
        sign = -1 if dec_str.startswith("-") else 1
        dec_parts = dec_str.lstrip("+-").split()
        dec_dec = sign * (float(dec_parts[0]) + float(dec_parts[1])/60)

    if filter_strategy == "LRGB":
        filters   = ",".join(DEFAULTS["lrgb_filters"])
        counts    = ",".join(str(c) for c in lrgb_counts)
        intervals = ",".join(str(interval) for _ in lrgb_counts)
        binnings  = "1,2,2,2"  # Luminance bin 1, RGB bin 2
    else:
        filters   = DEFAULTS["lum_filters"][0]
        counts    = str(lum_counts[0])
        intervals = str(interval)
        binnings  = "1"
```

With:

```python
    if ned_coords and arp_int in ned_coords:
        ra_dec, dec_dec = ned_coords[arp_int]
    else:
        ra_str = str(row["RA (J2000)"]).strip().split()
        ra_dec = float(ra_str[0]) + float(ra_str[1])/60 + (float(ra_str[2]) if len(ra_str)>2 else 0)/3600
        dec_str = str(row["Dec (J2000)"]).strip()
        sign = -1 if dec_str.startswith("-") else 1
        dec_parts = dec_str.lstrip("+-").split()
        dec_dec = sign * (float(dec_parts[0]) + float(dec_parts[1])/60)

    if filter_strategy == "LRGB":
        filters   = ",".join(LRGB_FILTERS)
        counts    = ",".join(str(c) for c in lrgb_counts)
        intervals = ",".join(str(interval) for _ in lrgb_counts)
        binnings  = "1,2,2,2"  # Luminance bin 1, RGB bin 2
    else:
        filters   = LUM_FILTERS[0]
        counts    = str(lum_counts[0])
        intervals = str(interval)
        binnings  = "1"
```

Changes: removed dead `" Dec"` branch (Bug 3), replaced `DEFAULTS["lrgb_filters"]` with `LRGB_FILTERS`, replaced `DEFAULTS["lum_filters"][0]` with `LUM_FILTERS[0]`.

- [ ] **Step 4: Update `run()` to use `load_targets(sheet_name=...)` instead of `load_targets(filepath, season)`**

Replace:

```python
    targets = load_targets(SEASONAL_PLAN_FILE, args.season)
```

With:

```python
    sheet_name = SEASON_SHEETS.get(args.season)
    if not sheet_name:
        print(f"Unknown season '{args.season}'. Choose from: {list(SEASON_SHEETS)}")
        sys.exit(1)
    targets = load_targets(sheet_name=sheet_name)
```

- [ ] **Step 5: Update `parse_args()` to use imported `SEASON_SHEETS` and `PLAN_TIERS`**

These already reference the module-level names. Since we removed the local definitions and imported them, they'll resolve to the imported versions. No code change needed — just verify.

- [ ] **Step 6: Verify output matches baseline**

```bash
python arp_acp_generator.py --season Spring --output-dir /tmp/arp_test/acp_plans
diff -r /tmp/arp_baseline/acp_plans /tmp/arp_test/acp_plans
```

Expected: No diff (identical plan files and summary CSV).

- [ ] **Step 7: Commit**

```bash
git add arp_acp_generator.py
git commit -m "Migrate arp_acp_generator.py to use arp_common"
```

---

### Task 7: Migrate `arp_session_planner.py` to use `arp_common` and fix bugs

This is the most complex migration — it has 3 bugs to fix alongside the extraction.

**Files:**
- Modify: `arp_session_planner.py`

- [ ] **Step 1: Replace imports and remove duplicated code**

Replace lines 1-70 (everything through `INTERVAL = 300`) with:

```python
#!/usr/bin/env python3
"""
Arp Catalog Nightly Session Planner
====================================
Given a date and observatory, computes which Arp targets are observable
that night, applies moon avoidance, sorts by optimal imaging order
(by transit time), and outputs a ranked target list + ready-to-use ACP plan.

Usage:
    python arp_session_planner.py [--date YYYY-MM-DD] [--site SITE]
                                  [--min-hours N] [--min-el DEG]
                                  [--plan-tier TIER] [--output-dir DIR]

Examples:
    # Tonight at New Mexico
    python arp_session_planner.py

    # Specific date at Spain
    python arp_session_planner.py --date 2026-05-10 --site Spain

    # Only targets with 3+ observable hours
    python arp_session_planner.py --site "New Mexico" --min-hours 3
"""

import argparse
import datetime
import json
import math
import sys
from pathlib import Path

import ephem

from arp_common import (
    OBSERVATORIES, SITE_MAP, TELESCOPE_TIERS, PLAN_TIERS,
    LRGB_COUNTS, LUM_COUNTS, INTERVAL,
    OVERHEAD_PER_TARGET_SECS, OVERHEAD_SESSION_SECS,
    RISK_LABELS,
    load_targets, load_rates, load_ned_coords,
    parse_ra, parse_dec, sanitize_name, moon_risk,
)
```

- [ ] **Step 2: Remove duplicated functions**

Delete these functions which are now imported:
- `load_targets()` (lines 77-86)
- `load_rates()` (lines 89-109) — this also fixes Bug 1 (bare `except:`) since `arp_common.load_rates()` uses proper exception types
- `load_ned_coords()` (lines 116-126)
- `parse_ra()` (lines 133-135)
- `parse_dec()` (lines 138-148)
- `sanitize_name()` (lines 151-154)
- `moon_risk()` (lines 161-166)

- [ ] **Step 3: Update `get_moon_info()` — moon risk now returns short codes**

The function body stays the same because `moon_risk()` is now imported and returns `"G"`/`"M"`/`"A"`. The dict it builds (`{"phase": ..., "sep": ..., "risk": risk}`) will now have short-code risk values. No change to `get_moon_info()` itself.

- [ ] **Step 4: Fix Bug 2 — apply `--min-el` override in `run()`**

At the top of `run()`, after `obs_key = args.site`, add the `--min-el` override by making a local copy of the config:

Replace:

```python
def run(args):
    date    = datetime.date.fromisoformat(args.date) if args.date else datetime.date.today()
    obs_key = args.site
    plan_tier = args.plan_tier

    print(f"\n{'='*60}")
    print(f"  Arp Nightly Session Planner")
    print(f"  Date: {date}  |  Site: {obs_key}  |  Tier: {plan_tier}")
    print(f"{'='*60}\n")

    ned_coords = load_ned_coords()
    if ned_coords:
        print(f"  NED coordinates loaded for {len(ned_coords)} targets.")
    else:
        print(f"  No arp_ned_coords.csv found — using catalog coordinates.")

    targets_df = load_targets()
    rates      = load_rates()

    # Dark window
    eve_twi, morn_twi = get_dark_window(obs_key, date)
    if eve_twi is None:
        print("  Could not compute dark window for this date/site.")
        sys.exit(1)

    cfg = OBSERVATORIES[obs_key]
```

With:

```python
def run(args):
    date    = datetime.date.fromisoformat(args.date) if args.date else datetime.date.today()
    obs_key = args.site
    plan_tier = args.plan_tier

    # Local copy of observatory config so --min-el override doesn't mutate shared dict
    cfg = dict(OBSERVATORIES[obs_key])
    if args.min_el is not None:
        cfg["min_el"] = args.min_el

    print(f"\n{'='*60}")
    print(f"  Arp Nightly Session Planner")
    print(f"  Date: {date}  |  Site: {obs_key}  |  Tier: {plan_tier}")
    if args.min_el is not None:
        print(f"  Min elevation: {args.min_el}° (override)")
    print(f"{'='*60}\n")

    ned_coords = load_ned_coords()
    if ned_coords:
        print(f"  NED coordinates loaded for {len(ned_coords)} targets.")
    else:
        print(f"  No arp_ned_coords.csv found — using catalog coordinates.")

    targets_df = load_targets()
    rates      = load_rates()

    # Dark window
    eve_twi, morn_twi = get_dark_window(obs_key, date, cfg)
    if eve_twi is None:
        print("  Could not compute dark window for this date/site.")
        sys.exit(1)
```

- [ ] **Step 5: Update `get_dark_window()` and `get_target_visibility()` to accept `cfg` dict**

Update `get_dark_window` to accept the config dict directly instead of looking it up:

Replace:

```python
def get_dark_window(obs_key, date):
    """Return (eve_twi, morn_twi) as ephem.Date floats, or (None, None)."""
    cfg = OBSERVATORIES[obs_key]
```

With:

```python
def get_dark_window(obs_key, date, cfg=None):
    """Return (eve_twi, morn_twi) as ephem.Date floats, or (None, None)."""
    if cfg is None:
        cfg = OBSERVATORIES[obs_key]
```

Update `get_target_visibility` similarly:

Replace:

```python
def get_target_visibility(ra_str, dec_str, obs_key, eve_twi, morn_twi):
    """
    Return dict with observable hours, start/end/transit times (UTC ephem floats),
    or None if not observable.
    """
    cfg      = OBSERVATORIES[obs_key]
```

With:

```python
def get_target_visibility(ra_str, dec_str, obs_key, eve_twi, morn_twi, cfg=None):
    """
    Return dict with observable hours, start/end/transit times (UTC ephem floats),
    or None if not observable.
    """
    if cfg is None:
        cfg = OBSERVATORIES[obs_key]
```

Then update the call in `run()` to pass `cfg`:

Replace:

```python
        vis = get_target_visibility(ra_str, dec_str, obs_key, eve_twi, morn_twi)
```

With:

```python
        vis = get_target_visibility(ra_str, dec_str, obs_key, eve_twi, morn_twi, cfg)
```

- [ ] **Step 6: Update rate access pattern**

`load_rates()` now returns `{tel: {"session": {...}, "exposure": {...}}}` instead of `{tel: {...}}`.

Replace:

```python
        rate = rates.get(tel, {}).get(plan_tier)
```

With:

```python
        rate = rates.get(tel, {}).get("session", {}).get(plan_tier)
```

- [ ] **Step 7: Replace magic numbers in `estimate_cost()` and `build_session_plan()`**

In `estimate_cost()`, replace:

```python
    overhead = 180  # slew + platesolve
```

With:

```python
    overhead = OVERHEAD_PER_TARGET_SECS
```

In `build_session_plan()`, replace:

```python
    overhead_secs = len(targets_tonight) * 180 + 300  # slew + startup
```

With:

```python
    overhead_secs = len(targets_tonight) * OVERHEAD_PER_TARGET_SECS + OVERHEAD_SESSION_SECS
```

- [ ] **Step 8: Update all moon risk comparisons (Bug 4)**

Replace all long-form risk string comparisons with short codes, and use `RISK_LABELS` for display only.

In `run()`, the moon filter (was line 482):

Replace:

```python
        if args.moon_ok_only and moon_info["risk"] == "Avoid":
```

With:

```python
        if args.moon_ok_only and moon_info["risk"] == "A":
```

The risk-category counts (was lines 521-523):

Replace:

```python
    good = [t for t in results if t["moon"]["risk"] != "Avoid"]
    marg = [t for t in results if t["moon"]["risk"] == "Marginal"]
    avoid = [t for t in results if t["moon"]["risk"] == "Avoid"]
```

With:

```python
    good = [t for t in results if t["moon"]["risk"] != "A"]
    marg = [t for t in results if t["moon"]["risk"] == "M"]
    avoid = [t for t in results if t["moon"]["risk"] == "A"]
```

The display line (was line 526):

Replace:

```python
        risk_flag = "  " if t["moon"]["risk"] == "Good" else ("~ " if t["moon"]["risk"] == "Marginal" else "! ")
```

With:

```python
        risk_flag = "  " if t["moon"]["risk"] == "G" else ("~ " if t["moon"]["risk"] == "M" else "! ")
```

The risk label in the table output (was line 532, the `{t['moon']['risk']:<8}` format):

Replace:

```python
              f"{t['moon']['risk']:<8}  {t['telescope']:>4}  {cost_str:>6}  {t['strategy']}")
```

With:

```python
              f"{RISK_LABELS[t['moon']['risk']]:<8}  {t['telescope']:>4}  {cost_str:>6}  {t['strategy']}")
```

In `build_session_plan()`, the moon string in the ACP comment (was line 368):

Replace:

```python
        moon_str = f"moon {t['moon']['phase']:.0f}% sep {t['moon']['sep']:.0f}deg"
```

This line doesn't reference risk, so no change needed. But ensure the `RISK_LABELS` import is available for any display that shows risk labels.

- [ ] **Step 9: Update `parse_args()` to use imported constants**

Replace:

```python
    parser.add_argument("--site", default="New Mexico",
        choices=list(OBSERVATORIES.keys()),
```

And:

```python
    parser.add_argument("--plan-tier", default="Plan-40",
        choices=PLAN_TIERS,
```

These already reference module-level names. Since locals are removed and imports are in place, they resolve correctly. No change needed.

- [ ] **Step 10: Verify output**

```bash
python arp_session_planner.py --site "New Mexico" --output-dir /tmp/arp_test/session_plans
```

**Expected differences from baseline** (these are intentional):
- The JSON file's `risk` fields will now contain `"G"`/`"M"`/`"A"` instead of `"Good"`/`"Marginal"`/`"Avoid"`. This is the Bug 4 fix — standardizing on short codes.
- The ACP plan text and console table should still display "Good", "Marginal", "Avoid" via `RISK_LABELS`.

Verify: The console "Risk" column still shows human-readable labels. The target count and ordering should be identical to baseline.

- [ ] **Step 11: Verify Bug 2 fix — `--min-el` now works**

```bash
# Default min_el=30
python arp_session_planner.py --site "New Mexico" --output-dir /tmp/arp_test/session_default 2>&1 | grep "observable targets"

# Higher min_el=45 should produce fewer targets
python arp_session_planner.py --site "New Mexico" --min-el 45 --output-dir /tmp/arp_test/session_45 2>&1 | grep "observable targets"
```

Expected: The `--min-el 45` run shows fewer observable targets.

- [ ] **Step 12: Commit**

```bash
git add arp_session_planner.py
git commit -m "Migrate arp_session_planner.py to arp_common; fix --min-el, bare except, moon risk codes"
```

---

### Task 8: Final validation and CLAUDE.md update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run all four scripts to verify no regressions**

```bash
python arp_acp_generator.py --season Spring --output-dir /tmp/arp_final/acp_plans
python arp_session_planner.py --site "New Mexico" --output-dir /tmp/arp_final/session_plans
python arp_moon_calendar.py --days 7 --output /tmp/arp_final/moon_data.json
python arp_ned_coords.py --help
```

All should complete without errors.

- [ ] **Step 2: Diff ACP plans and moon data against baseline**

```bash
diff -r /tmp/arp_baseline/acp_plans /tmp/arp_final/acp_plans
diff /tmp/arp_baseline/moon_data.json /tmp/arp_final/moon_data.json
```

Expected: No differences for ACP plans and moon data. The session planner JSON will have `"G"/"M"/"A"` risk codes instead of `"Good"/"Marginal"/"Avoid"` — this is the intentional Bug 4 fix.

- [ ] **Step 3: Update CLAUDE.md to document `arp_common.py`**

Add a bullet under "Architecture" that documents the new shared module. Replace the "Shared patterns across scripts" section's note about duplication with a note that shared code lives in `arp_common.py`.

In `CLAUDE.md`, replace:

```markdown
### Shared patterns across scripts
- All scripts use `Path(__file__).parent` as `DATA_DIR` — data files must live alongside scripts.
- Telescope assignment uses the same 4-tier size logic (`TELESCOPE_TIERS`) duplicated in `arp_acp_generator.py` and `arp_session_planner.py`.
- Moon risk classification (G/M/A) uses phase-dependent separation thresholds with a 20° `GOOD_MARGIN`, duplicated in `arp_moon_calendar.py` and `arp_session_planner.py`.
- Observatory coordinates/parameters are duplicated between `arp_moon_calendar.py` and `arp_session_planner.py`.
- NED coordinates (`arp_ned_coords.csv`) are auto-detected and preferred over catalog coords when present.
```

With:

```markdown
### Shared module (`arp_common.py`)
- All shared constants, data loaders, coordinate utilities, and moon risk classification live in `arp_common.py`, imported by all four scripts.
- `arp_common.py` must live alongside the scripts (same directory) — it uses `Path(__file__).parent` as `DATA_DIR`.
- Constants defined once: `OBSERVATORIES`, `SITE_MAP`, `TELESCOPE_TIERS`, `PHASE_THRESHOLDS`, `GOOD_MARGIN`, imaging defaults (`LRGB_COUNTS`, `LUM_COUNTS`, `INTERVAL`), overhead estimates.
- Data loaders: `load_targets()`, `load_telescopes()`, `load_rates()`, `load_ned_coords()`.
- Moon risk returns single-letter codes (`"G"`, `"M"`, `"A"`). Use `RISK_LABELS` dict for display names.
- NED coordinates (`arp_ned_coords.csv`) are auto-detected and preferred over catalog coords when present.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "Update CLAUDE.md to reflect arp_common.py shared module"
```

- [ ] **Step 5: Clean up baseline files**

```bash
rm -rf /tmp/arp_baseline /tmp/arp_test /tmp/arp_final
```
