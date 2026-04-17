"""Tests for the data migration script."""

import pytest
from app import create_app, db
from app.config import Config
from app.models import Target, Telescope, TelescopeRate


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


def test_import_targets_creates_338_rows(app):
    from scripts.migrate_data import import_targets
    with app.app_context():
        count = import_targets(db.session)
        assert count == 338
        t = db.session.query(Target).filter_by(arp_number=85).first()
        assert t is not None
        assert t.season in ("Spring", "Summer", "Autumn", "Winter")


def test_import_telescopes(app):
    from scripts.migrate_data import import_telescopes
    with app.app_context():
        count = import_telescopes(db.session)
        assert count > 0
        t17 = db.session.query(Telescope).filter_by(telescope_id="T17").first()
        assert t17 is not None
        assert t17.site is not None


def test_import_ned_coords(app):
    from scripts.migrate_data import import_targets, import_ned_coords
    with app.app_context():
        import_targets(db.session)
        ned_count = import_ned_coords(db.session)
        assert ned_count > 0
        with_ned = db.session.query(Target).filter(
            Target.ned_ra_hours.isnot(None)
        ).count()
        assert with_ned > 0
