"""Tests for the file import service."""

import pytest
from app.services.importer import detect_file_type


def test_detect_seasonal_plan():
    assert detect_file_type("Arp_Seasonal_Plan.xlsx") == "seasonal_plan"


def test_detect_telescope_file():
    assert detect_file_type("itelescopesystems.xlsx") == "telescopes"


def test_detect_ned_coords():
    assert detect_file_type("arp_ned_coords.csv") == "ned_coords"


def test_detect_unknown():
    assert detect_file_type("random.txt") is None
