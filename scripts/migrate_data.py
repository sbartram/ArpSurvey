#!/usr/bin/env python3
"""
One-time migration: flat files → PostgreSQL.

Usage:
    python scripts/migrate_data.py [--database-url URL] [--dry-run]
"""

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from arp_common import (
    SEASON_SHEETS, SITE_TELESCOPES, PLAN_TIERS,
    load_targets, load_telescopes, load_rates,
    parse_ra, parse_dec, DATA_DIR,
)
from app import create_app, db
from app.config import Config
from app.models import (
    Target, Telescope, TelescopeRate, MoonData, MoonCalendarRun,
)


def import_targets(session):
    """Import targets from Arp_Seasonal_Plan.xlsx into the targets table."""
    season_map = {}
    for season_name, sheet_name in SEASON_SHEETS.items():
        if season_name == "All":
            continue
        try:
            df = load_targets(sheet_name=sheet_name)
            for _, row in df.iterrows():
                arp = int(float(str(row["Arp #"]).strip()))
                season_map[arp] = season_name
        except Exception:
            continue

    df = load_targets(sheet_name="All Objects")
    count = 0

    for _, row in df.iterrows():
        arp = int(float(str(row["Arp #"]).strip()))
        name = str(row["Common Name"]).strip()
        ra_str = str(row["RA (J2000)"]).strip()
        dec_str = str(row["Dec (J2000)"]).strip()

        ra_parts = parse_ra(ra_str).split(":")
        ra_hours = float(ra_parts[0]) + float(ra_parts[1]) / 60
        if len(ra_parts) > 2:
            ra_hours += float(ra_parts[2]) / 3600

        dec_parsed = parse_dec(dec_str)
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
            existing.dec_catalog = dec_str
            existing.size_arcmin = size
            existing.season = season
            existing.best_site = best_site
            existing.filter_strategy = filter_strategy
        else:
            target = Target(
                arp_number=arp, name=name, ra_hours=ra_hours, dec_degrees=dec_degrees,
                ra_catalog=ra_str, dec_catalog=dec_str, size_arcmin=size,
                season=season, best_site=best_site, filter_strategy=filter_strategy,
            )
            session.add(target)
        count += 1

    session.flush()
    return count


def import_ned_coords(session):
    """Import NED coordinates from arp_ned_coords.csv."""
    ned_path = DATA_DIR / "arp_ned_coords.csv"
    if not ned_path.exists():
        return 0

    df = pd.read_csv(ned_path)
    count = 0

    for _, row in df.iterrows():
        if row.get("source") != "NED":
            continue
        arp = int(row["arp"])
        target = session.query(Target).filter_by(arp_number=arp).first()
        if target:
            target.ned_ra_hours = float(row["ra_hours"])
            target.ned_dec_degrees = float(row["dec_deg"])
            target.ned_name = str(row.get("ned_name", "")).strip() or None
            count += 1

    session.flush()
    return count


def import_telescopes(session):
    """Import telescope specs from itelescopesystems.xlsx."""
    tels_df = load_telescopes()
    count = 0

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

        resolution = None
        try:
            resolution = float(row.get("Resolution (arcsec/px)", None))
        except (ValueError, TypeError):
            pass

        aperture = None
        try:
            aperture = float(row.get("Aperture (mm)", None))
        except (ValueError, TypeError):
            pass

        existing = session.query(Telescope).filter_by(telescope_id=tel_id).first()
        if existing:
            existing.site = site
            existing.fov_arcmin = fov_x
            existing.resolution = resolution
            existing.aperture_mm = aperture
        else:
            tel = Telescope(
                telescope_id=tel_id, site=site, fov_arcmin=fov_x,
                resolution=resolution, aperture_mm=aperture,
            )
            session.add(tel)
        count += 1

    session.flush()
    return count


def import_rates(session):
    """Import telescope imaging rates."""
    rates = load_rates()
    count = 0

    for tel_id_str, rate_data in rates.items():
        tel = session.query(Telescope).filter_by(telescope_id=tel_id_str).first()
        if not tel:
            continue

        for plan_tier in PLAN_TIERS:
            session_rate = rate_data["session"].get(plan_tier)
            exposure_rate = rate_data["exposure"].get(plan_tier)

            existing = session.query(TelescopeRate).filter_by(
                telescope_id=tel.id, plan_tier=plan_tier
            ).first()

            if existing:
                existing.session_rate = session_rate
                existing.exposure_rate = exposure_rate
            else:
                rate = TelescopeRate(
                    telescope_id=tel.id, plan_tier=plan_tier,
                    session_rate=session_rate, exposure_rate=exposure_rate,
                )
                session.add(rate)
            count += 1

    session.flush()
    return count


def import_moon_data(session):
    """Import moon data from arp_moon_data.json."""
    moon_path = DATA_DIR / "arp_moon_data.json"
    if not moon_path.exists():
        return 0, False

    with open(moon_path) as f:
        data = json.load(f)

    run = MoonCalendarRun(
        status="complete",
        generated_at=datetime.now(timezone.utc),
        days=data["days"],
        site_key="New Mexico",
        start_date=date.fromisoformat(data["generated"]),
        phase_calendar=data.get("phase_cal", []),
        next_new_moon=date.fromisoformat(data["next_new"]) if data.get("next_new") else None,
        next_full_moon=date.fromisoformat(data["next_full"]) if data.get("next_full") else None,
    )
    session.add(run)
    session.flush()

    targets = {t.arp_number: t.id for t in session.query(Target).all()}

    count = 0
    for entry in data["targets"]:
        arp = entry["arp"]
        target_id = targets.get(arp)
        if not target_id:
            continue

        for w in entry["windows"]:
            moon = MoonData(
                target_id=target_id,
                night_date=date.fromisoformat(w["d"]),
                phase_pct=w["p"],
                separation_deg=w["s"],
                risk=w["r"],
            )
            session.add(moon)
            count += 1

    session.flush()
    return count, True


def main():
    parser = argparse.ArgumentParser(description="Migrate flat files to PostgreSQL")
    parser.add_argument("--database-url", default=None,
                        help="PostgreSQL URL (or set DATABASE_URL env var)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse and validate only, then rollback")
    args = parser.parse_args()

    if args.database_url:
        import os
        os.environ["DATABASE_URL"] = args.database_url

    app = create_app()

    with app.app_context():
        print("\n=== ArpSurvey Data Migration ===\n")

        target_count = import_targets(db.session)
        print(f"Targets imported:    {target_count}")

        ned_count = import_ned_coords(db.session)
        print(f"NED coords matched:  {ned_count}")

        tel_count = import_telescopes(db.session)
        print(f"Telescopes imported: {tel_count}")

        rate_count = import_rates(db.session)
        print(f"Rate entries:        {rate_count}")

        moon_count, moon_ok = import_moon_data(db.session)
        print(f"Moon data rows:      {moon_count}")

        if args.dry_run:
            db.session.rollback()
            print("\n[DRY RUN] All changes rolled back.\n")
        else:
            db.session.commit()
            print("\n[OK] Migration committed.\n")


if __name__ == "__main__":
    main()
