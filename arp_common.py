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
    "New Mexico": ["T2", "T5", "T11", "T14", "T20", "T21", "T24", "T25", "T26", "T68"],
    "Australia":  ["T8", "T17", "T30", "T32", "T33", "T59"],
    "Spain":      ["T18", "T80"],
    "Chile":      ["T70", "T71", "T72", "T73", "T74", "T75"],
}

# ---------------------------------------------------------------------------
# Telescope and plan configuration
# ---------------------------------------------------------------------------

# Telescope preference order for auto-assignment based on target angular size.
# Format: (min_arcmin, max_arcmin, preferred_telescope_ids_in_order)
# The first telescope in the list that has the target in its FOV will be used.
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
    Rates are in iTelescope points per hour.
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
