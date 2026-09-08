"""Azure OpenAI calls: tool-calling chat, streaming chat, embeddings."""

from __future__ import annotations

import json
from typing import Any, Iterator

import requests

import config

_http = requests.Session()


class LLMError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    return {"Content-Type": "application/json", "api-key": config.AZURE_OPENAI_KEY}


def chat(
    messages: list[dict],
    *,
    tools: list[dict] | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> dict:
    """One non-streaming completion. Returns the assistant message object."""
    if not config.llm_configured():
        raise LLMError("Azure OpenAI is not configured (AZURE_OPENAI_ENDPOINT / KEY)")

    body: dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens or config.CHAT_MAX_TOKENS,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"

    try:
        response = _http.post(
            config.AZURE_OPENAI_ENDPOINT,
            headers=_headers(),
            json=body,
            timeout=config.CHAT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.exceptions.Timeout as exc:
        raise LLMError("The assistant took too long to respond") from exc
    except requests.exceptions.HTTPError as exc:
        raise LLMError(
            f"Azure OpenAI error {exc.response.status_code}: {exc.response.text[:200]}"
        ) from exc
    except requests.RequestException as exc:
        raise LLMError(f"Could not reach Azure OpenAI: {exc}") from exc

    payload = response.json()
    try:
        return payload["choices"][0]["message"]
    except (KeyError, IndexError) as exc:
        raise LLMError(f"Unexpected Azure OpenAI response: {payload}") from exc


def stream_chat(
    messages: list[dict],
    *,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> Iterator[str]:
    """Stream assistant text deltas."""
    if not config.llm_configured():
        raise LLMError("Azure OpenAI is not configured (AZURE_OPENAI_ENDPOINT / KEY)")

    body = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens or config.CHAT_MAX_TOKENS,
        "stream": True,
    }

    try:
        response = _http.post(
            config.AZURE_OPENAI_ENDPOINT,
            headers=_headers(),
            json=body,
            timeout=config.CHAT_TIMEOUT_SECONDS,
            stream=True,
        )
        response.raise_for_status()
    except requests.exceptions.Timeout as exc:
        raise LLMError("The assistant took too long to respond") from exc
    except requests.exceptions.HTTPError as exc:
        raise LLMError(f"Azure OpenAI error {exc.response.status_code}") from exc
    except requests.RequestException as exc:
        raise LLMError(f"Could not reach Azure OpenAI: {exc}") from exc

    for raw in response.iter_lines(decode_unicode=True):
        if not raw or not raw.startswith("data: "):
            continue
        payload = raw[6:].strip()
        if payload == "[DONE]":
            break
        try:
            chunk = json.loads(payload)
            choices = chunk.get("choices") or []
            if not choices:
                continue
            text = (choices[0].get("delta") or {}).get("content")
            if text:
                yield text
        except json.JSONDecodeError:
            continue


def embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Raises if embeddings are not configured."""
    if not config.embeddings_configured():
        raise LLMError("Embeddings are not configured (AZURE_OPENAI_BASE / deployment)")

    try:
        response = _http.post(
            config.embedding_url(),
            headers=_headers(),
            json={"input": texts},
            timeout=config.CHAT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise LLMError(f"Embedding request failed: {exc}") from exc

    payload = response.json()
    rows = sorted(payload.get("data", []), key=lambda d: d.get("index", 0))
    return [row["embedding"] for row in rows]


def embed_one(text: str) -> list[float] | None:
    """Embed a single query, returning None if embeddings are unavailable."""
    if not config.embeddings_configured():
        return None
    try:
        return embed([text])[0]
    except (LLMError, IndexError, KeyError):
        return None
