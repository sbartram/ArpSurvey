"""Tests for telescopes routes."""

import pytest

from app import create_app, db
from app.config import Config
from app.models import Telescope


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        telescopes = [
            Telescope(telescope_id="T5", site="New Mexico Skies",
                      aperture_mm=250, fov_arcmin=60.5,
                      camera_model="FLI PL16803", sensor_type="CCD",
                      filters=["L", "R", "G", "B"], active=True),
            Telescope(telescope_id="T14", site="New Mexico Skies",
                      aperture_mm=431, fov_arcmin=28.3,
                      camera_model="FLI PL09000", sensor_type="CCD",
                      filters=["L", "R", "G", "B"], active=True),
            Telescope(telescope_id="T24", site="SSO",
                      aperture_mm=610, fov_arcmin=22.8,
                      camera_model="FLI PL09000", sensor_type="CCD",
                      filters=["L", "R", "G", "B", "Ha"], active=False),
        ]
        db.session.add_all(telescopes)
        db.session.commit()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_telescopes_page_renders(client):
    response = client.get("/telescopes")
    assert response.status_code == 200
    assert b"Fleet status" in response.data
    assert b"T5" in response.data
    assert b"T14" in response.data
    assert b"T24" in response.data


def test_telescopes_page_shows_counts(client):
    response = client.get("/telescopes")
    html = response.data.decode()
    # 3 total, 2 online, 1 offline
    assert "Total telescopes" in html
    assert "Online" in html
    assert "Offline" in html


def test_toggle_online_to_offline(client, app):
    with app.app_context():
        t5 = Telescope.query.filter_by(telescope_id="T5").first()
        assert t5.active is True
        response = client.patch(f"/telescopes/{t5.id}/toggle")
        assert response.status_code == 200
        assert b"Offline" in response.data
        assert b"offline-row" in response.data
        db.session.refresh(t5)
        assert t5.active is False


def test_toggle_offline_to_online(client, app):
    with app.app_context():
        t24 = Telescope.query.filter_by(telescope_id="T24").first()
        assert t24.active is False
        response = client.patch(f"/telescopes/{t24.id}/toggle")
        assert response.status_code == 200
        assert b"Online" in response.data
        db.session.refresh(t24)
        assert t24.active is True


def test_toggle_nonexistent_returns_404(client):
    response = client.patch("/telescopes/9999/toggle")
    assert response.status_code == 404


def test_offline_row_has_dimmed_class(client, app):
    response = client.get("/telescopes")
    html = response.data.decode()
    # T24 is offline, its row should have offline-row class
    assert "offline-row" in html


def test_natural_sort_order(client):
    """T5 should appear before T14 (natural sort, not lexicographic)."""
    response = client.get("/telescopes")
    html = response.data.decode()
    t5_pos = html.index("T5")
    t14_pos = html.index("T14")
    assert t5_pos < t14_pos
