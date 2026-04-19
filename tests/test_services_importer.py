"""Tests for the file import service (app/services/importer.py).

Covers: detect_file_type, import_ned_coords_file.
"""

import io
import pytest
from pathlib import Path

from app import create_app, db
from app.config import Config
from app.models import Target
from app.services.importer import detect_file_type, import_ned_coords_file


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
# detect_file_type
# ---------------------------------------------------------------------------

def test_detect_seasonal_plan():
    assert detect_file_type("Arp_Seasonal_Plan.xlsx") == "seasonal_plan"


def test_detect_telescope_file():
    assert detect_file_type("itelescopesystems.xlsx") == "telescopes"


def test_detect_ned_coords():
    assert detect_file_type("arp_ned_coords.csv") == "ned_coords"


def test_detect_unknown():
    assert detect_file_type("random.txt") is None


def test_detect_case_insensitive():
    assert detect_file_type("ARP_SEASONAL_PLAN.XLSX") == "seasonal_plan"


def test_detect_ned_coords_variant():
    assert detect_file_type("my_ned_coords_v2.csv") == "ned_coords"


# ---------------------------------------------------------------------------
# import_ned_coords_file — integration
# ---------------------------------------------------------------------------

class FakeFileStorage:
    """Minimal stand-in for Flask's FileStorage."""

    def __init__(self, content: str, filename: str = "test.csv"):
        self._content = content.encode("utf-8")
        self.filename = filename

    def save(self, dst):
        dst.write(self._content)


class TestImportNedCoords:
    def test_imports_ned_coordinates(self, session):
        t = Target(arp_number=1, name="NGC 2857", ra_hours=9.0, dec_degrees=49.0, season="Spring")
        session.add(t)
        session.flush()

        csv_content = (
            "arp,ra_hours,dec_deg,ned_name,source\n"
            "1,9.3725,49.3631,NGC 2857,NED\n"
        )
        storage = FakeFileStorage(csv_content)
        result = import_ned_coords_file(storage, session)

        assert result["updated"] == 1
        assert t.ned_ra_hours == pytest.approx(9.3725)
        assert t.ned_dec_degrees == pytest.approx(49.3631)
        assert t.ned_name == "NGC 2857"

    def test_skips_non_ned_source(self, session):
        t = Target(arp_number=1, name="NGC 2857", ra_hours=9.0, dec_degrees=49.0, season="Spring")
        session.add(t)
        session.flush()

        csv_content = (
            "arp,ra_hours,dec_deg,ned_name,source\n"
            "1,9.0,49.0,NGC 2857,SIMBAD\n"
        )
        storage = FakeFileStorage(csv_content)
        result = import_ned_coords_file(storage, session)

        assert result["updated"] == 0
        assert t.ned_ra_hours is None

    def test_skips_missing_targets(self, session):
        csv_content = (
            "arp,ra_hours,dec_deg,ned_name,source\n"
            "999,1.0,2.0,Missing,NED\n"
        )
        storage = FakeFileStorage(csv_content)
        result = import_ned_coords_file(storage, session)

        assert result["updated"] == 0

    def test_multiple_targets(self, session):
        t1 = Target(arp_number=1, name="NGC 2857", ra_hours=9.0, dec_degrees=49.0, season="Spring")
        t2 = Target(arp_number=2, name="UGC 10310", ra_hours=16.3, dec_degrees=47.2, season="Summer")
        session.add_all([t1, t2])
        session.flush()

        csv_content = (
            "arp,ra_hours,dec_deg,ned_name,source\n"
            "1,9.3725,49.3631,NGC 2857,NED\n"
            "2,16.2852,47.1722,UGC 10310,NED\n"
            "3,10.0,20.0,Missing,NED\n"
        )
        storage = FakeFileStorage(csv_content)
        result = import_ned_coords_file(storage, session)

        assert result["updated"] == 2
        assert t1.ned_ra_hours == pytest.approx(9.3725)
        assert t2.ned_ra_hours == pytest.approx(16.2852)

    def test_ned_name_empty_becomes_none(self, session):
        t = Target(arp_number=1, name="NGC 2857", ra_hours=9.0, dec_degrees=49.0, season="Spring")
        session.add(t)
        session.flush()

        csv_content = (
            "arp,ra_hours,dec_deg,ned_name,source\n"
            "1,9.3725,49.3631,,NED\n"
        )
        storage = FakeFileStorage(csv_content)
        import_ned_coords_file(storage, session)

        assert t.ned_name is None
