"""Settings from backend/.env.

Unlike the FixFeels reference, missing credentials do not raise at import time.
The app starts in a degraded mode instead, so the UI and retrieval can be
demonstrated offline and /api/health reports exactly what is missing.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_ENV_FILE = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_FILE)


def _get(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


# ── Azure OpenAI ────────────────────────────────────────────────────
# Chat endpoint is the full deployment URL including ?api-version=,
# matching the FixFeels convention.
AZURE_OPENAI_ENDPOINT: str = _get("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY: str = _get("AZURE_OPENAI_KEY")

# Embeddings: base resource URL + deployment name (used to build the URL).
AZURE_OPENAI_BASE: str = _get("AZURE_OPENAI_BASE")
AZURE_EMBEDDING_DEPLOYMENT: str = _get("AZURE_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
AZURE_EMBEDDING_API_VERSION: str = _get("AZURE_EMBEDDING_API_VERSION", "2024-02-01")

# ── Azure Speech ────────────────────────────────────────────────────
AZURE_SPEECH_KEY: str = _get("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION: str = _get("AZURE_SPEECH_REGION")

# ── App ─────────────────────────────────────────────────────────────
CORS_ORIGINS: str = _get("CORS_ORIGINS")

# Guard the Speech token endpoint. The FixFeels build left /api/stt-token open,
# which lets anyone mint Speech tokens against the subscription. Set this and
# the frontend must send it as X-Client-Key.
CLIENT_KEY: str = _get("CLIENT_KEY")

# Build the embedding index on first start when it is missing. The index is
# 71 MB and not in git, so a fresh App Service deploy has none. App Service
# /home is persistent, so this costs one embedding pass per deployment, not per
# restart. Off by default so nobody is surprised by the API spend.
BUILD_INDEX_ON_STARTUP: bool = _get("BUILD_INDEX_ON_STARTUP", "").lower() in {"1", "true", "yes"}

MAX_TOOL_ROUNDS: int = int(_get("MAX_TOOL_ROUNDS", "4"))
CHAT_MAX_TOKENS: int = int(_get("CHAT_MAX_TOKENS", "450"))
CHAT_TIMEOUT_SECONDS: int = int(_get("CHAT_TIMEOUT_SECONDS", "45"))


def cors_origins() -> list[str]:
    """Honour CORS_ORIGINS; fall back to open only when unset (dev)."""
    origins = [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
    return origins or ["*"]


def llm_configured() -> bool:
    return bool(AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY)


def speech_configured() -> bool:
    return bool(AZURE_SPEECH_KEY and AZURE_SPEECH_REGION)


def embeddings_configured() -> bool:
    return bool(AZURE_OPENAI_BASE and AZURE_OPENAI_KEY and AZURE_EMBEDDING_DEPLOYMENT)


def embedding_url() -> str:
    base = AZURE_OPENAI_BASE.rstrip("/")
    return (
        f"{base}/openai/deployments/{AZURE_EMBEDDING_DEPLOYMENT}/embeddings"
        f"?api-version={AZURE_EMBEDDING_API_VERSION}"
    )


def missing_settings() -> list[str]:
    missing = []
    if not llm_configured():
        missing.append("AZURE_OPENAI_ENDPOINT/AZURE_OPENAI_KEY (chat)")
    if not speech_configured():
        missing.append("AZURE_SPEECH_KEY/AZURE_SPEECH_REGION (voice)")
    if not embeddings_configured():
        missing.append("AZURE_OPENAI_BASE/AZURE_EMBEDDING_DEPLOYMENT (semantic search)")
    return missing
