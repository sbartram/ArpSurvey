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
