"""Tests for the session planner service."""

import datetime
import pytest
from app.services.session import compute_session


def test_compute_session_returns_observable_targets():
    targets = [
        {"arp_number": 85, "name": "M51", "ra_hours": 13.5, "dec_degrees": 47.2,
         "size_arcmin": 11.0, "filter_strategy": "LRGB", "best_site": "New Mexico / Spain"},
    ]
    results = compute_session(
        date=datetime.date(2026, 4, 17),
        site_key="New Mexico",
        targets=targets,
        min_hours=1.0,
        moon_filter="",
    )
    assert len(results) >= 1
    r = results[0]
    assert r["arp"] == 85
    assert r["hours"] > 0
    assert r["moon"]["risk"] in ("G", "M", "A")


def test_compute_session_filters_by_min_hours():
    targets = [
        {"arp_number": 85, "name": "M51", "ra_hours": 13.5, "dec_degrees": 47.2,
         "size_arcmin": 11.0, "filter_strategy": "LRGB", "best_site": "New Mexico / Spain"},
    ]
    results = compute_session(
        date=datetime.date(2026, 4, 17),
        site_key="New Mexico",
        targets=targets,
        min_hours=99,
        moon_filter="",
    )
    assert len(results) == 0


def test_compute_session_filters_by_site():
    targets = [
        {"arp_number": 1, "name": "Test", "ra_hours": 13.5, "dec_degrees": 47.2,
         "size_arcmin": 3.0, "filter_strategy": "Luminance",
         "best_site": "Australia"},
    ]
    results = compute_session(
        date=datetime.date(2026, 4, 17),
        site_key="New Mexico",
        targets=targets,
        min_hours=1.0,
        moon_filter="",
    )
    assert len(results) == 0
