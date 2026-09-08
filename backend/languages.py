"""Supported languages: STT locales, TTS voices, and script detection.

Azure constraints that shape this list (verified against Microsoft Learn,
2026-09):

* Continuous language identification accepts at most 10 candidate locales
  (4 for at-start). Accuracy falls as candidates are added, so the demo set is
  deliberately small.
* LID cannot switch language *within* a sentence. Indian callers code-mix
  constantly ("report kab aayega, is it 24 hours?"), so Hindi and English are
  treated as one bucket: hi-IN recognition tolerates embedded English, and the
  model is told to mirror whatever mix the customer used.
* Text to speech covers only 8 Indian locales. Bengali, Punjabi, Odia, Urdu and
  Assamese have speech to text but NO neural voice — those can be offered in
  text chat but cannot be spoken back. `tts_voice` is None for them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    locale: str
    name: str          # English name, for the system prompt
    native_name: str   # for the UI picker
    tts_voice: str | None
    stt_candidate: bool = True


# Demo set. Hindi and English first — LID resolves the common case fastest when
# the likeliest candidates lead.
LANGUAGES: tuple[Language, ...] = (
    Language("hi-IN", "Hindi", "हिन्दी", "hi-IN-Kavya:MAI-Voice-2"),
    Language("en-IN", "Indian English", "English", "en-IN-Aarti:DragonHDLatestNeural"),
    Language("bn-IN", "Bengali", "বাংলা", None),
    Language("ta-IN", "Tamil", "தமிழ்", "ta-IN-JarulNeural"),
    Language("te-IN", "Telugu", "తెలుగు", "te-IN-ShrutiNeural"),
    Language("mr-IN", "Marathi", "मराठी", "mr-IN-AarohiNeural"),
)

BY_LOCALE = {lang.locale: lang for lang in LANGUAGES}
DEFAULT_LOCALE = "hi-IN"
FALLBACK_TTS_VOICE = "en-IN-Aarti:DragonHDLatestNeural"


def stt_candidates() -> list[str]:
    """Candidate locales for Azure continuous LID (max 10; we send 6)."""
    return [lang.locale for lang in LANGUAGES if lang.stt_candidate]


def get(locale: str | None) -> Language:
    return BY_LOCALE.get((locale or "").strip(), BY_LOCALE[DEFAULT_LOCALE])


def tts_voice_for(locale: str | None) -> str:
    """Voice for a locale, falling back to the Indian English voice.

    Bengali has no Azure neural voice, so a Bengali reply is spoken by the
    en-IN voice. It reads the Bengali text with an English phonology — poor,
    but better than silence. Flagged in /api/languages as speakable=false so
    the UI can hide the speaker control instead.
    """
    language = get(locale)
    return language.tts_voice or FALLBACK_TTS_VOICE


def can_speak(locale: str | None) -> bool:
    return get(locale).tts_voice is not None


# ── script detection ────────────────────────────────────────────────
# Used when the client sends no locale (typed chat). Script is a reliable
# signal for Indic languages; it cannot separate Hindi from Marathi (both
# Devanagari), so that pair falls back to the client hint or Hindi.

_SCRIPTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("bn-IN", re.compile(r"[ঀ-৿]")),
    ("ta-IN", re.compile(r"[஀-௿]")),
    ("te-IN", re.compile(r"[ఀ-౿]")),
    ("hi-IN", re.compile(r"[ऀ-ॿ]")),  # Devanagari: Hindi or Marathi
)


# Romanised-Hindi cues. Latin script alone cannot separate "mujhe seene mein
# dard" from "I have chest pain", and getting it wrong means handing someone an
# emergency instruction in a language they may not read — so content decides,
# not the session's language setting.
_ROMAN_HINDI = re.compile(
    r"\b(mujhe|mera|meri|mere|hai|hain|nahi|nahin|kya|kaise|kab|kitna|kitne|kaha|"
    r"raha|rahi|karo|kar|kro|aap|aapka|apna|ji|haan|bhai|please\s+batao|batao|"
    r"bataye|chahiye|krna|karna|hona|ho\s+raha|dard|test\s+karwana)\b",
    re.IGNORECASE,
)


def detect_locale(text: str, hint: str | None = None) -> str:
    """Best-effort locale, used for the TTS voice and for safety replies."""
    text = text or ""

    for locale, pattern in _SCRIPTS:
        if pattern.search(text):
            # Devanagari is shared — trust a Marathi hint from the client.
            if locale == "hi-IN" and (hint or "") == "mr-IN":
                return "mr-IN"
            return locale

    # Latin script: decide from the words themselves.
    if _ROMAN_HINDI.search(text):
        return "mr-IN" if (hint or "") == "mr-IN" else "hi-IN"

    # No Indic script and no Hindi cues — treat it as English rather than
    # inheriting a hint the customer may have never chosen.
    return "en-IN"


def catalogue() -> list[dict]:
    """Shape the frontend language picker consumes."""
    return [
        {
            "locale": lang.locale,
            "name": lang.name,
            "native_name": lang.native_name,
            "speakable": lang.tts_voice is not None,
        }
        for lang in LANGUAGES
    ]
