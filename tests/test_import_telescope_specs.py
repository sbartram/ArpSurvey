"""Tests for the telescope specs import script (scripts/import_telescope_specs.py).

Covers: parse_filters, parse_qe, parse_full_well, parse_pixel_size,
parse_focal_length, get_sensor_specs, and integration with the DB.
"""

import csv
import pytest
from pathlib import Path

from scripts.import_telescope_specs import (
    parse_filters, parse_qe, parse_full_well, parse_pixel_size,
    parse_focal_length, get_sensor_specs, import_telescope_csv,
    import_magnitudes,
)
from arp_common import SITE_UTAH, SITE_SPAIN
from app import create_app, db
from app.config import Config
from app.models import Target, Telescope


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def session(app):
    with app.app_context():
        yield db.session


# ---------------------------------------------------------------------------
# parse_filters
# ---------------------------------------------------------------------------

class TestParseFilters:
    def test_lrgb_shorthand(self):
        result = parse_filters("LRGB, Ha (5nm), SII(5nm), OIII(5nm), V Filters")
        assert set(result) == {"L", "R", "G", "B", "Ha", "SII", "OIII"}

    def test_longhand_filter_names(self):
        result = parse_filters("Luminance, Red, Green, Blue")
        assert set(result) == {"L", "R", "G", "B"}

    def test_narrowband_only(self):
        result = parse_filters("Astrodon Ha (3nm), SII (3nm) & OIII (5nm)")
        assert set(result) == {"Ha", "SII", "OIII"}

    def test_multi_line_description(self):
        raw = ("Chroma Filters:\n"
               "Wideband: Luminance, Red, Green & Blue\n"
               "Narrowband: SII, Ha & OIII with a 3nm optimise passband")
        result = parse_filters(raw)
        assert set(result) == {"L", "R", "G", "B", "Ha", "SII", "OIII"}

    def test_comma_separated_letters(self):
        result = parse_filters("L,R,G,B,SII,Ha,OIII,U,V,B,R,I filters")
        assert "L" in result
        assert "Ha" in result

    def test_clear_treated_as_luminance(self):
        result = parse_filters(
            "Red Green Blue, Ha, SII, OIII, Clear and Johnson's Cousin's Photometric"
        )
        assert "L" in result
        assert set(result) >= {"L", "R", "G", "B", "Ha"}

    def test_none_string(self):
        assert parse_filters("None") is None

    def test_empty_string(self):
        assert parse_filters("") is None

    def test_none_value(self):
        assert parse_filters(None) is None

    def test_dash(self):
        assert parse_filters("—") is None

    def test_returns_sorted(self):
        result = parse_filters("LRGB, Ha, SII, OIII")
        assert result == sorted(result)

    def test_ha_with_underscore(self):
        result = parse_filters("3nm Ha3_50R, Sii3_50R, Oiii_50R")
        assert "Ha" in result
        assert "SII" in result
        assert "OIII" in result


# ---------------------------------------------------------------------------
# parse_qe
# ---------------------------------------------------------------------------

class TestParseQe:
    def test_plain_percentage(self):
        assert parse_qe("91%") == 0.91

    def test_gt_prefix(self):
        assert parse_qe(">80%") == 0.80

    def test_with_wavelength(self):
        assert parse_qe("91% (475nm)") == 0.91

    def test_dash(self):
        assert parse_qe("—") is None

    def test_none(self):
        assert parse_qe(None) is None

    def test_empty(self):
        assert parse_qe("") is None


# ---------------------------------------------------------------------------
# parse_full_well
# ---------------------------------------------------------------------------

class TestParseFullWell:
    def test_integer_ke(self):
        assert parse_full_well("100Ke") == 100_000

    def test_decimal_ke(self):
        assert parse_full_well("51Ke") == 51_000

    def test_fractional_ke(self):
        assert parse_full_well("71.6Ke") == 71_600

    def test_with_space(self):
        assert parse_full_well("50 Ke") == 50_000

    def test_dash(self):
        assert parse_full_well("—") is None

    def test_none(self):
        assert parse_full_well(None) is None

    def test_empty(self):
        assert parse_full_well("") is None


# ---------------------------------------------------------------------------
# parse_pixel_size
# ---------------------------------------------------------------------------

class TestParsePixelSize:
    def test_plain_number(self):
        assert parse_pixel_size("3.76") == 3.76

    def test_with_bin_suffix(self):
        assert parse_pixel_size("9 (Bin2)") == 9.0

    def test_none(self):
        assert parse_pixel_size(None) is None

    def test_empty(self):
        assert parse_pixel_size("") is None


# ---------------------------------------------------------------------------
# parse_focal_length
# ---------------------------------------------------------------------------

class TestParseFocalLength:
    def test_plain_integer(self):
        assert parse_focal_length("2280") == 2280.0

    def test_with_reducer_note(self):
        assert parse_focal_length("2280\n(0.66 reducer)") == 2280.0

    def test_resolution_with_arcsec(self):
        """Also used for resolution values like '0.81"'."""
        assert parse_focal_length('0.81"') == 0.81

    def test_aperture_plain(self):
        assert parse_focal_length("510") == 510.0

    def test_none(self):
        assert parse_focal_length(None) is None

    def test_empty(self):
        assert parse_focal_length("") is None


# ---------------------------------------------------------------------------
# get_sensor_specs
# ---------------------------------------------------------------------------

class TestGetSensorSpecs:
    def test_cmos_sensor_match(self):
        specs = get_sensor_specs("ASI6200MM Pro", "Sony IMX455")
        assert specs["read_noise"] == 1.5
        assert specs["dark_current"] == 0.001

    def test_camera_model_fallback(self):
        specs = get_sensor_specs("SBIG STX-16803", "—")
        assert specs["read_noise"] == 9.0
        assert specs["dark_current"] == 0.04

    def test_camera_model_case_insensitive(self):
        specs = get_sensor_specs("fli microline 16803", None)
        assert specs["read_noise"] == 9.0

    def test_unknown_returns_empty(self):
        assert get_sensor_specs("Unknown Camera", None) == {}

    def test_both_none(self):
        assert get_sensor_specs(None, None) == {}

    def test_cmos_preferred_over_camera(self):
        """CMOS sensor model takes priority when both match."""
        specs = get_sensor_specs("SBIG STX-16803", "Sony IMX455")
        assert specs["read_noise"] == 1.5


# ---------------------------------------------------------------------------
# import_telescope_csv — integration
# ---------------------------------------------------------------------------

CSV_FIELDNAMES = [
    "Telescope", "Platform", "Aperture (in)", "Aperature (mm)",
    "Focal Length (mm)", "F-Ratio", "Optical Tube Assembly", "Optical Design",
    "Camera", "Sensor Type", "CMOS Sensor Model", "Sensor Size / Format (mm)",
    'Camera Angle\n("Up" = Deg. East of N)',
    "FOV X (arcmins)", "FOV Y (arcmins)", "Pixel Size (µm)",
    "Resolution (arcsec / pixel)", "Sensor Megapixels", "Array X", "Array Y",
    "Peak QE", "Full Well", "N/ABG", "Recommended Max Exposure (seconds)",
    "Guiding", "Mount", "Filters", "Notes",
    "Additional System Specifications\n(e.g. horizon limits, special notes)",
]


def _write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            # Fill missing fields with empty strings
            full = {k: row.get(k, "") for k in CSV_FIELDNAMES}
            writer.writerow(full)


@pytest.fixture
def fixture_csv(tmp_path):
    """Create a minimal itelescopes.csv fixture."""
    csv_path = tmp_path / "itelescopes.csv"
    _write_csv(csv_path, [{
        "Telescope": "T99",
        "Aperature (mm)": "508",
        "Focal Length (mm)": "2280",
        "Camera": "ASI6200MM Pro (mono)",
        "Sensor Type": "CMOS",
        "CMOS Sensor Model": "Sony IMX455",
        "Pixel Size (µm)": "3.76",
        "Resolution (arcsec / pixel)": '0.34"',
        "Peak QE": "91% (475nm)",
        "Full Well": "51.4Ke",
        "Filters": "Astrodon LRGB, Ha (5nm), SII (5nm), OIII (5nm)",
    }])
    return csv_path


class TestImportTelescopeCsv:
    def test_imports_all_fields(self, session, fixture_csv):
        """Verify every parsed field lands in the DB."""
        tel = Telescope(telescope_id="T99", site=SITE_UTAH)
        session.add(tel)
        session.flush()

        count = import_telescope_csv(session, csv_path=fixture_csv)
        assert count == 1

        tel = session.query(Telescope).filter_by(telescope_id="T99").first()
        assert tel.aperture_mm == 508.0
        assert tel.focal_length_mm == 2280.0
        assert tel.resolution == 0.34
        assert tel.pixel_size_um == 3.76
        assert tel.peak_qe == 0.91
        assert tel.full_well_e == 51_400
        assert tel.camera_model == "ASI6200MM Pro (mono)"
        assert tel.sensor_model == "Sony IMX455"
        assert tel.sensor_type == "CMOS"
        assert tel.read_noise_e == 1.5
        assert tel.dark_current_e == 0.001
        assert set(tel.filters) == {"L", "R", "G", "B", "Ha", "SII", "OIII"}

    def test_skips_unknown_telescope(self, session, fixture_csv):
        """Telescope not in DB should be silently skipped."""
        count = import_telescope_csv(session, csv_path=fixture_csv)
        assert count == 0

    def test_updates_existing_telescope(self, session, fixture_csv):
        """Running import twice should update, not duplicate."""
        tel = Telescope(telescope_id="T99", site=SITE_UTAH, aperture_mm=100.0)
        session.add(tel)
        session.flush()

        import_telescope_csv(session, csv_path=fixture_csv)
        assert tel.aperture_mm == 508.0  # updated from 100 to 508

    def test_missing_csv_returns_zero(self, session, tmp_path):
        missing = tmp_path / "nonexistent.csv"
        count = import_telescope_csv(session, csv_path=missing)
        assert count == 0

    def test_ccd_sensor_type_normalized(self, session, tmp_path):
        csv_path = tmp_path / "itelescopes.csv"
        _write_csv(csv_path, [{
            "Telescope": "T88",
            "Sensor Type": "CCD (Mono, Cooled to -30C)",
            "Camera": "SBIG STX-16803",
            "CMOS Sensor Model": "—",
        }])
        tel = Telescope(telescope_id="T88", site=SITE_UTAH)
        session.add(tel)
        session.flush()

        import_telescope_csv(session, csv_path=csv_path)
        assert tel.sensor_type == "CCD"

    def test_handles_none_filters(self, session, tmp_path):
        csv_path = tmp_path / "itelescopes.csv"
        _write_csv(csv_path, [{
            "Telescope": "T88",
            "Filters": "None",
        }])
        tel = Telescope(telescope_id="T88", site=SITE_SPAIN)
        session.add(tel)
        session.flush()

        import_telescope_csv(session, csv_path=csv_path)
        assert tel.filters is None


# ---------------------------------------------------------------------------
# import_magnitudes — integration
# ---------------------------------------------------------------------------

@pytest.fixture
def fixture_tsv(tmp_path):
    """Create a minimal asu.tsv fixture."""
    tsv_path = tmp_path / "asu.tsv"
    tsv_path.write_text(
        "# Arp | Name | VT\n"
        "1|NGC 2857|12.2\n"
        "1|Component B|14.5\n"   # should keep brightest (12.2)
        "2|NGC 2857B|13.8\n"
        "999|Missing|10.0\n"     # no matching target in DB
    )
    return tsv_path


class TestImportMagnitudes:
    def test_imports_brightest_magnitude(self, session, fixture_tsv):
        t1 = Target(arp_number=1, name="NGC 2857", ra_hours=9.0, dec_degrees=49.0, season="Spring")
        t2 = Target(arp_number=2, name="NGC 2857B", ra_hours=9.1, dec_degrees=49.1, season="Spring")
        session.add_all([t1, t2])
        session.flush()

        count = import_magnitudes(session, tsv_path=fixture_tsv)
        assert count == 2

        assert t1.magnitude == 12.2  # brightest of 12.2 and 14.5
        assert t2.magnitude == 13.8

    def test_skips_targets_not_in_db(self, session, fixture_tsv):
        """Arp 999 has no target row, should be skipped."""
        t1 = Target(arp_number=1, name="NGC 2857", ra_hours=9.0, dec_degrees=49.0, season="Spring")
        session.add(t1)
        session.flush()

        count = import_magnitudes(session, tsv_path=fixture_tsv)
        assert count == 1

    def test_missing_tsv_returns_zero(self, session, tmp_path):
        missing = tmp_path / "nonexistent.tsv"
        count = import_magnitudes(session, tsv_path=missing)
        assert count == 0

    def test_skips_comment_and_empty_lines(self, session, tmp_path):
        tsv = tmp_path / "asu.tsv"
        tsv.write_text(
            "# comment\n"
            "----------\n"
            "\n"
            "5|NGC 3664|14.1\n"
        )
        t = Target(arp_number=5, name="NGC 3664", ra_hours=11.0, dec_degrees=3.0, season="Spring")
        session.add(t)
        session.flush()

        count = import_magnitudes(session, tsv_path=tsv)
        assert count == 1
        assert t.magnitude == 14.1
