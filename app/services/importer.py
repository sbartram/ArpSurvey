"""
File import service.

Handles uploading and importing Excel/CSV files into the database.
Detection is filename-based; parsing reuses arp_common data loaders.
"""

import tempfile
from pathlib import Path

import pandas as pd

from arp_common import (
    SEASON_SHEETS, SITE_TELESCOPES, PLAN_TIERS,
    load_targets, load_telescopes, load_rates,
    parse_ra, parse_dec,
)
from app import db
from app.models import Target, Telescope, TelescopeRate


def detect_file_type(filename):
    """Detect file type from filename. Returns type string or None."""
    name = filename.lower()
    if "seasonal_plan" in name and name.endswith(".xlsx"):
        return "seasonal_plan"
    if "itelescopesystems" in name and name.endswith(".xlsx"):
        return "telescopes"
    if "ned_coords" in name and name.endswith(".csv"):
        return "ned_coords"
    return None


def import_seasonal_plan(file_storage, session):
    """
    Import target data from an uploaded Arp_Seasonal_Plan.xlsx.
    Returns summary dict: {imported, updated, errors}.
    """
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        file_storage.save(tmp)
        tmp_path = Path(tmp.name)

    try:
        season_map = {}
        for season_name, sheet_name in SEASON_SHEETS.items():
            if season_name == "All":
                continue
            try:
                df = pd.read_excel(tmp_path, sheet_name=sheet_name, header=None)
                header_row = None
                for i, row in df.iterrows():
                    if any(str(v).strip() == "Arp #" for v in row.values):
                        header_row = i
                        break
                if header_row is not None:
                    df.columns = df.iloc[header_row]
                    df = df.iloc[header_row + 1:].reset_index(drop=True)
                    df = df.dropna(subset=["Arp #"])
                    for _, row in df.iterrows():
                        arp = int(float(str(row["Arp #"]).strip()))
                        season_map[arp] = season_name
            except Exception:
                continue

        df = pd.read_excel(tmp_path, sheet_name="All Objects", header=None)
        header_row = None
        for i, row in df.iterrows():
            if any(str(v).strip() == "Arp #" for v in row.values):
                header_row = i
                break
        df.columns = df.iloc[header_row]
        df = df.iloc[header_row + 1:].reset_index(drop=True)
        df = df.dropna(subset=["Arp #"])
        df.columns = [str(c).strip() for c in df.columns]

        imported = 0
        updated = 0

        for _, row in df.iterrows():
            arp = int(float(str(row["Arp #"]).strip()))
            name = str(row["Common Name"]).strip()
            ra_str = str(row["RA (J2000)"]).strip()
            dec_str_raw = str(row["Dec (J2000)"]).strip()

            ra_parts = parse_ra(ra_str).split(":")
            ra_hours = float(ra_parts[0]) + float(ra_parts[1]) / 60
            if len(ra_parts) > 2:
                ra_hours += float(ra_parts[2]) / 3600

            dec_parsed = parse_dec(dec_str_raw)
            sign = -1 if dec_parsed.startswith("-") else 1
            dec_parts = dec_parsed.lstrip("+-").split(":")
            dec_degrees = sign * (
                float(dec_parts[0]) + float(dec_parts[1]) / 60 + float(dec_parts[2]) / 3600
            )

            try:
                size = float(row["Size (arcmin)"])
            except (ValueError, TypeError):
                size = None

            best_site = str(row.get("Best Site", "")).strip()
            filter_strategy = str(row.get("Filter Strategy", "Luminance")).strip()
            season = season_map.get(arp, "Spring")

            existing = session.query(Target).filter_by(arp_number=arp).first()
            if existing:
                existing.name = name
                existing.ra_hours = ra_hours
                existing.dec_degrees = dec_degrees
                existing.ra_catalog = ra_str
                existing.dec_catalog = dec_str_raw
                existing.size_arcmin = size
                existing.season = season
                existing.best_site = best_site
                existing.filter_strategy = filter_strategy
                updated += 1
            else:
                target = Target(
                    arp_number=arp, name=name, ra_hours=ra_hours,
                    dec_degrees=dec_degrees, ra_catalog=ra_str,
                    dec_catalog=dec_str_raw, size_arcmin=size,
                    season=season, best_site=best_site,
                    filter_strategy=filter_strategy,
                )
                session.add(target)
                imported += 1

        session.commit()
        return {"imported": imported, "updated": updated, "errors": 0}
    finally:
        tmp_path.unlink(missing_ok=True)


def import_telescopes_file(file_storage, session):
    """Import telescope data from uploaded itelescopesystems.xlsx."""
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        file_storage.save(tmp)
        tmp_path = Path(tmp.name)

    try:
        tels_df = load_telescopes(filepath=str(tmp_path))
        rates_data = load_rates(filepath=str(tmp_path))
        tel_count = 0
        rate_count = 0

        for tel_id, row in tels_df.iterrows():
            site = "Unknown"
            for site_name, site_tels in SITE_TELESCOPES.items():
                if tel_id in site_tels:
                    site = site_name
                    break

            fov_x = None
            try:
                fov_x = float(row.get("FOV X (arcmins)", None))
            except (ValueError, TypeError):
                pass

            existing = session.query(Telescope).filter_by(telescope_id=tel_id).first()
            if existing:
                existing.site = site
                existing.fov_arcmin = fov_x
            else:
                tel = Telescope(telescope_id=tel_id, site=site, fov_arcmin=fov_x)
                session.add(tel)
            tel_count += 1

        session.flush()

        for tel_id_str, rate_data in rates_data.items():
            tel = session.query(Telescope).filter_by(telescope_id=tel_id_str).first()
            if not tel:
                continue
            for plan_tier in PLAN_TIERS:
                existing = session.query(TelescopeRate).filter_by(
                    telescope_id=tel.id, plan_tier=plan_tier
                ).first()
                if existing:
                    existing.session_rate = rate_data["session"].get(plan_tier)
                    existing.exposure_rate = rate_data["exposure"].get(plan_tier)
                else:
                    rate = TelescopeRate(
                        telescope_id=tel.id, plan_tier=plan_tier,
                        session_rate=rate_data["session"].get(plan_tier),
                        exposure_rate=rate_data["exposure"].get(plan_tier),
                    )
                    session.add(rate)
                rate_count += 1

        session.commit()
        return {"telescopes": tel_count, "rates": rate_count}
    finally:
        tmp_path.unlink(missing_ok=True)


def import_ned_coords_file(file_storage, session):
    """Import NED coordinates from uploaded arp_ned_coords.csv."""
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        file_storage.save(tmp)
        tmp_path = Path(tmp.name)

    try:
        df = pd.read_csv(tmp_path)
        count = 0

        for _, row in df.iterrows():
            if row.get("source") != "NED":
                continue
            arp = int(row["arp"])
            target = session.query(Target).filter_by(arp_number=arp).first()
            if target:
                target.ned_ra_hours = float(row["ra_hours"])
                target.ned_dec_degrees = float(row["dec_deg"])
                raw_name = row.get("ned_name", "")
                target.ned_name = str(raw_name).strip() if pd.notna(raw_name) else None
                count += 1

        session.commit()
        return {"updated": count}
    finally:
        tmp_path.unlink(missing_ok=True)
