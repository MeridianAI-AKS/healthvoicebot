"""Prepare text for Azure TTS.

Adapted from the FixFeels reference with one deliberate change: that version
stripped *all* punctuation, including the Devanagari danda, to stop the English
voice inserting long pauses. In Indic scripts the danda is the sentence marker,
so removing it flattens the prosody into one long run-on. Here only markup,
emoji and stage directions are removed; sentence punctuation is kept, and
xml:lang is set per locale so the voice applies the right phonology.
"""

from __future__ import annotations

import re

_STRIP = (
    (re.compile(r"```.*?```", re.S), " "),
    (re.compile(r"`+"), ""),
    (re.compile(r"\*+|_{2,}"), ""),
    (re.compile(r"#{1,6}\s*"), ""),
    (re.compile(r"\[([^\]]*)\]\([^)]*\)"), r"\1"),          # [text](url) -> text
    (re.compile(r"\((?:smile|laugh|pause|wink|grin|sad)\)", re.I), ""),
    (re.compile(r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF☀-⛿]"), ""),
    (re.compile(r"[{}\[\]<>|\\]"), " "),
)

# Spoken forms for things a voice reads badly.
_SPEAKABLE = (
    (re.compile(r"https?://\S+"), " our website "),
    (re.compile(r"\bRs\.?\s*(\d)", re.I), r"\1 rupees "),
    (re.compile(r"₹\s*(\d)"), r"\1 rupees "),
    (re.compile(r"(\w)@(\w)"), r"\1 at \2"),
)


def prepare_text_for_tts(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    for pattern, replacement in _STRIP:
        cleaned = pattern.sub(replacement, cleaned)
    for pattern, replacement in _SPEAKABLE:
        cleaned = pattern.sub(replacement, cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def escape_ssml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def build_ssml(text: str, *, voice: str, locale: str = "en-IN") -> str:
    body = escape_ssml(prepare_text_for_tts(text))
    if not body:
        return ""
    return (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        f'xml:lang="{locale}">'
        f'<voice name="{voice}">{body}</voice>'
        f"</speak>"
    )
