"""Deterministic language detection for the answer-language loop (specs/003).

The system prompt asking the model to reply in the user's language is a *soft*
constraint the model sometimes ignores (it defaults to French because the data is
French). This module gives a deterministic detector so the service can:
  detect the question's language → instruct the model → verify the answer → repair.
"""

from __future__ import annotations

from langdetect import DetectorFactory, LangDetectException, detect

DetectorFactory.seed = 0  # make langdetect deterministic

# Codes we name explicitly in instructions; others fall back to the raw code.
LANG_NAMES = {
    "en": "English",
    "fr": "French",
    "ar": "Arabic",
    "es": "Spanish",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
}


def detect_language(text: str | None) -> str | None:
    """Best-effort ISO-639-1 code (e.g. 'en', 'fr'), or None if undetectable.

    Strips digits/punctuation-heavy fragments implicitly (langdetect ignores them);
    short or code-only strings return None so we don't force a wrong language."""
    if not text or len(text.strip()) < 3:
        return None
    try:
        return detect(text)
    except LangDetectException:
        return None


def language_name(code: str | None) -> str | None:
    return LANG_NAMES.get(code, code) if code else None
