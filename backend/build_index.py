"""Embed the knowledge corpus for semantic search.

    python build_index.py

Needs AZURE_OPENAI_BASE, AZURE_OPENAI_KEY and AZURE_EMBEDDING_DEPLOYMENT.
Without it the agent still works — retrieval falls back to BM25 keyword search.
Writes data/embeddings.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import config
from documents import build_documents
from llm import LLMError, embed

OUT_PATH = Path(__file__).parent / "data" / "embeddings.json"
BATCH_SIZE = 64


def main() -> None:
    if not config.embeddings_configured():
        print(
            "Embeddings not configured. Set AZURE_OPENAI_BASE, AZURE_OPENAI_KEY and\n"
            "AZURE_EMBEDDING_DEPLOYMENT in backend/.env, or skip this step and let the\n"
            "agent use keyword search.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    documents = build_documents()
    print(f"Embedding {len(documents)} documents in batches of {BATCH_SIZE}...")

    vectors: dict[str, list[float]] = {}
    for start in range(0, len(documents), BATCH_SIZE):
        batch = documents[start : start + BATCH_SIZE]
        # Title plus search text: the title carries the package name, which is
        # what most queries actually key on.
        payload = [f"{d.title}\n{d.search_text}"[:8000] for d in batch]
        try:
            embeddings = embed(payload)
        except LLMError as exc:
            print(f"  ! batch at {start} failed: {exc}", file=sys.stderr)
            continue
        for document, vector in zip(batch, embeddings):
            vectors[document.doc_id] = vector
        print(f"  {min(start + BATCH_SIZE, len(documents))}/{len(documents)}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "model": config.AZURE_EMBEDDING_DEPLOYMENT,
                "document_count": len(vectors),
                "vectors": vectors,
            },
            f,
        )
    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
