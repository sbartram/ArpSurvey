#!/usr/bin/env python3
"""
Import telescope CCD specs from itelescopes.csv and target magnitudes from asu.tsv.
"""

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app, db
from app.models import Telescope, Target

# Read noise and dark current by sensor model (published specs at operating temp)
SENSOR_SPECS = {
    "Sony IMX455": {"read_noise": 1.5, "dark_current": 0.001},
    "Sony IMX571": {"read_noise": 1.5, "dark_current": 0.0005},
    "Sony IMX410": {"read_noise": 1.2, "dark_current": 0.002},
    "KAF-3200ME":  {"read_noise": 8.8, "dark_current": 0.5},     # SBIG ST-10XME
    "KAI-11002M":  {"read_noise": 11.0, "dark_current": 0.008},  # FLI PL11002M
    "KAF-16803":   {"read_noise": 9.0, "dark_current": 0.04},    # STX-16803, FLI 16803, Alta U16
    "KAF-6303E":   {"read_noise": 12.0, "dark_current": 0.008},  # FLI PL6303E
    "KAF-16200":   {"read_noise": 8.0, "dark_current": 0.01},    # FLI ML-16200
}

# Camera model → sensor model mapping for cameras where the CSV doesn't list sensor
CAMERA_TO_SENSOR = {
    "SBIG ST-10XME": "KAF-3200ME",
    "FLI ProLine PL11002M": "KAI-11002M",
    "SBIG STX-16803": "KAF-16803",
    "FLI-PL6303E": "KAF-6303E",
    "FLI Proline 16803": "KAF-16803",
    "FLI PL16803": "KAF-16803",
    "FLI Microline 16803": "KAF-16803",
    "FLI ML-16200": "KAF-16200",
    "Apogee Alta U16": "KAF-16803",
    "FLI Proline PL16803": "KAF-16803",
}


def parse_full_well(val):
    """Parse full well like '51Ke' or '100Ke' to integer electrons."""
    if not val or val == "—":
        return None
    m = re.match(r"([\d.]+)\s*Ke", str(val))
    if m:
        return int(float(m.group(1)) * 1000)
    return None


def parse_qe(val):
    """Parse QE like '91%' or '>80%' or '91% (475nm)' to float 0-1."""
    if not val or val == "—":
        return None
    m = re.match(r">?\s*([\d.]+)\s*%", str(val))
    if m:
        return float(m.group(1)) / 100.0
    return None


def parse_pixel_size(val):
    """Parse pixel size, handling 'N (BinM)' format."""
    if not val:
        return None
    m = re.match(r"([\d.]+)", str(val))
    if m:
        return float(m.group(1))
    return None


def parse_focal_length(val):
    """Parse focal length, handling '2280\n(0.66 reducer)' format."""
    if not val:
        return None
    m = re.match(r"([\d.]+)", str(val).strip())
    if m:
        return float(m.group(1))
    return None


def get_sensor_specs(camera_model, cmos_sensor_model):
    """Look up read noise and dark current from sensor/camera model."""
    # Try CMOS sensor model first
    if cmos_sensor_model and cmos_sensor_model != "—":
        for key, specs in SENSOR_SPECS.items():
            if key in cmos_sensor_model:
                return specs

    # Try camera model mapping
    if camera_model:
        for cam_key, sensor_key in CAMERA_TO_SENSOR.items():
            if cam_key.lower() in camera_model.lower():
                return SENSOR_SPECS.get(sensor_key, {})

    return {}


def parse_filters(raw):
    """Parse free-text filter descriptions into standardized filter codes."""
    if not raw or raw.strip().lower() in ("none", "—", ""):
        return None
    text = raw.upper()
    found = set()
    # Check for LRGB shorthand first
    if "LRGB" in text:
        found.update(["L", "R", "G", "B"])
    else:
        if "LUMINANCE" in text or re.search(r'\bL\b', text):
            found.add("L")
        if re.search(r'\bRED\b', text) or re.search(r'\bR\b(?!C)', text):
            found.add("R")
        if re.search(r'\bGREEN\b', text) or re.search(r'(?<![A-Z])\bG\b', text):
            found.add("G")
        if re.search(r'\bBLUE\b', text) or re.search(r'(?<![A-Z])\bB\b(?!V)', text):
            found.add("B")
    if re.search(r'H[- ]?A(LPHA)?|HA[_3]', text):
        found.add("Ha")
    if re.search(r'S\s*II|SII', text):
        found.add("SII")
    if re.search(r'O\s*III|OIII', text):
        found.add("OIII")
    return sorted(found) if found else None


def import_telescope_csv(session, csv_path=None):
    if csv_path is None:
        csv_path = Path(__file__).resolve().parent.parent / "itelescopes.csv"
    if not csv_path.exists():
        print(f"  {csv_path} not found, skipping")
        return 0

    count = 0
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            tel_id = (row.get("Telescope") or "").strip()
            if not tel_id or not tel_id.startswith("T"):
                continue

            tel = session.query(Telescope).filter_by(telescope_id=tel_id).first()
            if not tel:
                continue

            camera = (row.get("Camera") or "").strip()
            sensor_model = (row.get("CMOS Sensor Model") or "").strip()
            sensor_type = (row.get("Sensor Type") or "").strip()
            # Simplify sensor type
            if "CCD" in sensor_type:
                sensor_type = "CCD"
            elif "CMOS" in sensor_type:
                sensor_type = "CMOS"

            tel.camera_model = camera or None
            tel.sensor_model = sensor_model if sensor_model != "—" else None
            tel.sensor_type = sensor_type or None
            tel.aperture_mm = parse_focal_length(row.get("Aperature (mm)"))  # CSV typo
            tel.focal_length_mm = parse_focal_length(row.get("Focal Length (mm)"))
            tel.resolution = parse_focal_length(row.get("Resolution (arcsec / pixel)"))
            tel.pixel_size_um = parse_pixel_size(row.get("Pixel Size (µm)"))
            tel.peak_qe = parse_qe(row.get("Peak QE"))
            tel.full_well_e = parse_full_well(row.get("Full Well"))

            specs = get_sensor_specs(camera, sensor_model)
            tel.read_noise_e = specs.get("read_noise")
            tel.dark_current_e = specs.get("dark_current")

            tel.filters = parse_filters(row.get("Filters"))

            count += 1

    session.flush()
    return count


def import_magnitudes(session, tsv_path=None):
    """Import V-band magnitudes from asu.tsv into targets."""
    if tsv_path is None:
        tsv_path = Path(__file__).resolve().parent.parent / "asu.tsv"
    if not tsv_path.exists():
        print(f"  {tsv_path} not found, skipping")
        return 0

    # Parse asu.tsv — format is pipe-delimited with Arp# in first column, VT (mag) in 3rd
    mag_map = {}  # arp_number → brightest magnitude
    with open(tsv_path, encoding='utf-8') as f:
        for line in f:
            if line.startswith('#') or line.startswith('-') or not line.strip():
                continue
            parts = line.split('|')
            if len(parts) < 3:
                continue
            try:
                arp = int(parts[0].strip())
                mag_str = parts[2].strip()
                if mag_str:
                    mag = float(mag_str)
                    # Keep the brightest (lowest) magnitude per Arp object
                    if arp not in mag_map or mag < mag_map[arp]:
                        mag_map[arp] = mag
            except (ValueError, IndexError):
                continue

    count = 0
    for arp, mag in mag_map.items():
        target = session.query(Target).filter_by(arp_number=arp).first()
        if target:
            target.magnitude = mag
            count += 1

    session.flush()
    return count


def main():
    app = create_app()
    with app.app_context():
        print("\n=== Import Telescope Specs & Magnitudes ===\n")

        tel_count = import_telescope_csv(db.session)
        print(f"Telescopes updated: {tel_count}")

        mag_count = import_magnitudes(db.session)
        print(f"Target magnitudes:  {mag_count}")

        db.session.commit()
        print("\n[OK] Done.\n")

        # Verify
        tels = db.session.query(Telescope).filter(
            Telescope.read_noise_e.isnot(None)
        ).all()
        print(f"Telescopes with CCD specs: {len(tels)}")
        for t in tels:
            print(f"  {t.telescope_id}: {t.camera_model}, RN={t.read_noise_e}e-, "
                  f"DC={t.dark_current_e}e-/s, QE={t.peak_qe}, FW={t.full_well_e}e-")


if __name__ == "__main__":
    main()
