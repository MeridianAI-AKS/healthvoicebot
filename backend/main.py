"""Hindustan Wellness multilingual help desk — FastAPI backend."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

import requests
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

import chat
import config
import languages
import session as sessions
from retrieval import get_retriever
from tts_text import build_ssml

_http = requests.Session()
_speech_token: str | None = None
_speech_token_expires: float = 0.0

TTS_OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Warm the index at startup so the first customer does not pay for it.
    try:
        retriever = get_retriever()
        print(f"Knowledge base ready: {len(retriever.documents)} docs ({retriever.mode})")
    except FileNotFoundError as exc:
        print(f"Warning: {exc}")

    if config.speech_configured():
        try:
            _issue_speech_token()
            print("Speech token warmed.")
        except Exception as exc:
            print(f"Warning: could not warm speech token: {exc}")

    missing = config.missing_settings()
    if missing:
        print("Running degraded — missing: " + "; ".join(missing))
    yield


app = FastAPI(title="Hindustan Wellness Help Desk API", lifespan=lifespan)

# Honour the configured origins. The reference hardcoded two origins here and
# ignored its own CORS_ORIGINS setting; this reads the setting.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── models ───────────────────────────────────────────────────────────

class StartRequest(BaseModel):
    locale: str | None = None


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    locale: str | None = None


class TTSRequest(BaseModel):
    text: str
    locale: str | None = None


# ── speech ───────────────────────────────────────────────────────────

def _issue_speech_token() -> str:
    global _speech_token, _speech_token_expires
    now = time.time()
    if _speech_token and now < _speech_token_expires:
        return _speech_token

    response = _http.post(
        f"https://{config.AZURE_SPEECH_REGION}.api.cognitive.microsoft.com"
        "/sts/v1.0/issueToken",
        headers={"Ocp-Apim-Subscription-Key": config.AZURE_SPEECH_KEY},
        timeout=10,
    )
    response.raise_for_status()
    _speech_token = response.text
    _speech_token_expires = now + 540  # tokens last 10 minutes
    return _speech_token


def _require_client_key(provided: str | None) -> None:
    """Gate the Speech token endpoint when CLIENT_KEY is configured.

    Left open, this endpoint mints Azure Speech tokens for anyone who finds it —
    the reference build's most exploitable surface.
    """
    if config.CLIENT_KEY and provided != config.CLIENT_KEY:
        raise HTTPException(401, "Missing or invalid client key")


# ── routes ───────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    try:
        retriever = get_retriever()
        docs, mode = len(retriever.documents), retriever.mode
    except FileNotFoundError:
        docs, mode = 0, "unavailable"

    return {
        "status": "ok" if docs else "degraded",
        "knowledge_documents": docs,
        "retrieval_mode": mode,
        "languages": [lang.locale for lang in languages.LANGUAGES],
        "llm": config.llm_configured(),
        "speech": config.speech_configured(),
        "embeddings": config.embeddings_configured(),
        "active_sessions": sessions.count(),
        "missing": config.missing_settings(),
    }


@app.get("/api/languages")
def language_list():
    return {
        "languages": languages.catalogue(),
        "stt_candidates": languages.stt_candidates(),
        "default": languages.DEFAULT_LOCALE,
    }


@app.post("/api/session/start")
def start_session(req: StartRequest | None = None):
    locale = (req.locale if req else None) or languages.DEFAULT_LOCALE
    if locale not in languages.BY_LOCALE:
        locale = languages.DEFAULT_LOCALE

    state = sessions.create(locale)
    reply = chat.greeting(locale)
    state.append("assistant", reply)

    return {
        "session_id": state.session_id,
        "locale": locale,
        "speakable": languages.can_speak(locale),
        "reply": reply,
    }


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest):
    if not req.message or not req.message.strip():
        raise HTTPException(400, "message is required")

    state = sessions.get(req.session_id)
    if not state:
        # Recover rather than fail: a restarted backend should not dead-end a demo.
        state = sessions.create(req.locale or languages.DEFAULT_LOCALE)

    def generate():
        yield from chat.process_turn(state, req.message, locale_hint=req.locale)

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"X-Session-Id": state.session_id, "Cache-Control": "no-cache"},
    )


@app.post("/api/tts")
def tts(req: TTSRequest):
    if not config.speech_configured():
        raise HTTPException(503, "Azure Speech is not configured")

    text = (req.text or "").strip()
    if not text:
        raise HTTPException(400, "text is required")

    locale = languages.detect_locale(text, hint=req.locale)
    voice = languages.tts_voice_for(locale)
    ssml = build_ssml(text, voice=voice, locale=locale)
    if not ssml:
        raise HTTPException(400, "nothing speakable in that text")

    try:
        token = _issue_speech_token()
    except Exception as exc:
        raise HTTPException(502, f"Could not get speech token: {exc}")

    try:
        audio = _http.post(
            f"https://{config.AZURE_SPEECH_REGION}.tts.speech.microsoft.com"
            "/cognitiveservices/v1",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": TTS_OUTPUT_FORMAT,
            },
            data=ssml.encode("utf-8"),
            timeout=25,
        )
        audio.raise_for_status()
    except Exception as exc:
        raise HTTPException(502, f"Speech synthesis failed: {exc}")

    return Response(
        content=audio.content,
        media_type="audio/mpeg",
        headers={"X-Voice": voice, "X-Locale": locale},
    )


@app.get("/api/stt-token")
def stt_token(x_client_key: str | None = Header(default=None)):
    _require_client_key(x_client_key)
    if not config.speech_configured():
        raise HTTPException(503, "Azure Speech is not configured")
    try:
        return {
            "token": _issue_speech_token(),
            "region": config.AZURE_SPEECH_REGION,
            "candidates": languages.stt_candidates(),
        }
    except Exception as exc:
        raise HTTPException(502, f"Could not issue speech token: {exc}")
