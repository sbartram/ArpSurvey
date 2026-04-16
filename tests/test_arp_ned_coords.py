"""Tests for arp_ned_coords.py name normalization."""

from arp_ned_coords import ned_query_names


def test_standard_catalog_name_first():
    candidates = ned_query_names("NGC 2535", 82)
    assert candidates[0] == "NGC 2535"
    assert candidates[-1] == "Arp 82"


def test_compound_name_splits_on_plus():
    """Compound like 'NGC 2535 + 56' queries primary first."""
    candidates = ned_query_names("NGC 2535 + 56", 82)
    assert candidates[0] == "NGC 2535"
    assert candidates[-1] == "Arp 82"


def test_messier_format_produces_m_variants():
    candidates = ned_query_names("MESSIER 51", 85)
    assert "M  51" in candidates  # double-space variant
    assert "M 51" in candidates   # single-space variant
    assert candidates[-1] == "Arp 85"


def test_stephans_quint_alias():
    candidates = ned_query_names("Stephan's Quint", 319)
    assert "Stephan's Quintet" in candidates


def test_holmberg_alias():
    candidates = ned_query_names("Holmberg II", 268)
    assert "Holmberg II" in candidates


def test_unknown_name_still_includes_arp_fallback():
    """Any unrecognized name still includes 'Arp NNN' as last fallback."""
    candidates = ned_query_names("WeirdSomething", 999)
    assert candidates[-1] == "Arp 999"


def test_arp_fallback_always_last():
    """Arp fallback is always the last item, regardless of input."""
    for name, num in [
        ("NGC 1234", 1),
        ("MESSIER 51", 85),
        ("Holmberg II", 268),
        ("Unknown", 999),
    ]:
        candidates = ned_query_names(name, num)
        assert candidates[-1] == f"Arp {num}"


def test_deduplicates_candidates():
    """No duplicate entries in the candidate list."""
    candidates = ned_query_names("NGC 1234", 1)
    assert len(candidates) == len(set(candidates))
