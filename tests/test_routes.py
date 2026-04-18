"""Tests for Flask routes."""

import pytest

from app import create_app, db
from app.config import Config
from app.models import Target


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        t = Target(
            arp_number=1,
            name="Test Galaxy",
            ra_hours=9.0,
            dec_degrees=49.0,
            season="Spring",
            status="Pending",
        )
        db.session.add(t)
        db.session.commit()
        yield app
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_overview_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Arp Catalog" in response.data
    assert b"Total targets" in response.data


def test_overview_shows_target_count(client):
    response = client.get("/")
    assert b"1" in response.data
