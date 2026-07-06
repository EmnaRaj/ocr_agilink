"""Deterministic language detection (specs/003 — answer-language loop)."""

from app.agent.lang import detect_language, language_name


def test_detects_english():
    assert detect_language("How many fiches are in review right now?") == "en"


def test_detects_french():
    assert detect_language("Combien de fiches sont en revue actuellement ?") == "fr"


def test_short_or_empty_returns_none():
    assert detect_language("") is None
    assert detect_language("   ") is None
    assert detect_language("10109362") is None  # code-only → no language forced


def test_language_name_maps_known_codes():
    assert language_name("en") == "English"
    assert language_name("fr") == "French"
    assert language_name(None) is None
