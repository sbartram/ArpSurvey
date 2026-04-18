"""Tests for Flask app factory and health endpoint."""

import pytest
from app import create_app, db
from app.config import Config


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
def client(app):
    return app.test_client()


def test_app_creates_successfully(app):
    assert app is not None
    assert app.config["TESTING"] is True


def test_health_endpoint_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
