"""Supported languages: STT locales, TTS voices, and script detection.

Azure constraints that shape this list (LID limits from Microsoft Learn, voices
verified against the live Speech resource, 2026-09):

* Continuous language identification accepts at most 10 candidate locales
  (4 for at-start). Accuracy falls as candidates are added, so the demo set is
  deliberately small.
* LID cannot switch language *within* a sentence. Indian callers code-mix
  constantly ("report kab aayega, is it 24 hours?"), so Hindi and English are
  treated as one bucket: hi-IN recognition tolerates embedded English, and the
  model is told to mirror whatever mix the customer used.
* Voice availability is per region and must be read from the Speech resource
  itself, not from the docs. The published language-support table omits bn-IN,
  but westus2 serves bn-IN-TanishaaNeural, and it lists ta-IN-JarulNeural,
  which this region does not have. Every voice below was verified against
  /cognitiveservices/voices/list on the live resource (westus2, 772 voices).
  Re-check when moving region: `python languages.py` prints a verification.

* A locale with no voice at all keeps `tts_voice = None`. Do not synthesise its
  text with another locale's voice — Azure returns 200 with an empty body
  rather than an error, which is silence the caller cannot diagnose.
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
    Language("bn-IN", "Bengali", "বাংলা", "bn-IN-TanishaaNeural"),
    Language("ta-IN", "Tamil", "தமிழ்", "ta-IN-PallaviNeural"),
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


def tts_voice_for(locale: str | None) -> tuple[str, str]:
    """(voice, xml_lang) for a locale.

    When a locale has no voice, fall back to the Indian English voice *and* to
    its own locale for xml:lang. Pairing a voice with a foreign xml:lang makes
    Azure return an empty audio body with a 200, which is indistinguishable
    from success until someone notices nothing played.
    """
    language = get(locale)
    if language.tts_voice:
        return language.tts_voice, language.locale
    return FALLBACK_TTS_VOICE, "en-IN"


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


if __name__ == "__main__":
    # Verify every configured voice exists in the current Speech region.
    import sys

    import requests

    import config

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not config.speech_configured():
        raise SystemExit("Azure Speech is not configured.")

    response = requests.get(
        f"https://{config.AZURE_SPEECH_REGION}.tts.speech.microsoft.com"
        "/cognitiveservices/voices/list",
        headers={"Ocp-Apim-Subscription-Key": config.AZURE_SPEECH_KEY},
        timeout=45,
    )
    response.raise_for_status()
    available = {v["ShortName"] for v in response.json()}

    print(f"Region {config.AZURE_SPEECH_REGION}: {len(available)} voices\n")
    missing = False
    for language in LANGUAGES:
        if language.tts_voice is None:
            print(f"  --   {language.locale}: no voice configured (text only)")
        elif language.tts_voice in available:
            print(f"  OK   {language.locale}: {language.tts_voice}")
        else:
            missing = True
            alternatives = sorted(
                v for v in available if v.startswith(f"{language.locale}-")
            )
            print(f"  MISS {language.locale}: {language.tts_voice} not in this region")
            print(f"       available: {', '.join(alternatives) or 'none'}")
    raise SystemExit(1 if missing else 0)
