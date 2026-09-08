"""Search over the knowledge corpus.

Two backends, used together when both are available:

* BM25 keyword search — always available, no credentials, no build step.
* Embedding search — needs Azure OpenAI embeddings and a built index
  (`python build_index.py`). Handles paraphrase and cross-language matching.

Multilingual note: the agent calls `search_catalogue` with an *English* query
even when the customer wrote in Bengali or Tamil, because the model translates
the intent as it forms the tool call. That keeps keyword search useful for every
language. Embeddings improve recall further but are not required for the demo.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from documents import Document, build_documents

INDEX_PATH = Path(__file__).parent / "data" / "embeddings.json"

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)

# BM25 parameters — standard defaults.
_K1 = 1.5
_B = 0.75

# Re-ranking. Tuned against the smoke queries in `python retrieval.py`.
_TITLE_BOOST = 1.8
_KIND_WEIGHT = {"package": 1.25, "company": 1.45, "faq": 0.7}


def _stem(token: str) -> str:
    """Crude English suffix stripping so 'fast' matches 'fasting'.

    Only applied to ASCII tokens — Indic words do not take these suffixes and
    would be mangled by the same rules.
    """
    if not token.isascii() or len(token) <= 4:
        return token
    for suffix in ("ing", "ies", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def tokenize(text: str) -> list[str]:
    return [_stem(t.lower()) for t in _TOKEN.findall(text or "") if len(t) > 1]


@dataclass
class Hit:
    document: Document
    score: float


class KeywordIndex:
    """Plain BM25. ~1,900 short documents, so a dict index is plenty."""

    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents
        self.doc_tokens = [tokenize(d.search_text) for d in documents]
        self.doc_len = [len(t) for t in self.doc_tokens]
        self.avg_len = (sum(self.doc_len) / len(self.doc_len)) if self.doc_len else 0.0

        self.term_freq: list[Counter[str]] = [Counter(t) for t in self.doc_tokens]
        doc_freq: Counter[str] = Counter()
        for tokens in self.doc_tokens:
            doc_freq.update(set(tokens))

        total = len(documents) or 1
        self.idf = {
            term: math.log(1 + (total - freq + 0.5) / (freq + 0.5))
            for term, freq in doc_freq.items()
        }
        self.postings: dict[str, list[int]] = {}
        for index, tokens in enumerate(self.doc_tokens):
            for term in set(tokens):
                self.postings.setdefault(term, []).append(index)

    def search(self, query: str, limit: int = 6) -> list[Hit]:
        terms = tokenize(query)
        if not terms:
            return []

        scores: dict[int, float] = {}
        for term in terms:
            idf = self.idf.get(term)
            if idf is None:
                continue
            for index in self.postings.get(term, ()):
                freq = self.term_freq[index][term]
                length = self.doc_len[index] or 1
                denominator = freq + _K1 * (1 - _B + _B * length / (self.avg_len or 1))
                scores[index] = scores.get(index, 0.0) + idf * freq * (_K1 + 1) / denominator

        # Plain BM25 ranks a two-line taxonomy stub above the package a customer
        # actually asked for, because short documents win on length normalisation.
        # Two corrections: reward overlap with the document *title* (which carries
        # the package name people search by), and prefer packages over the FAQ
        # entries that merely quote a package name.
        query_terms = set(terms)
        for index in list(scores):
            document = self.documents[index]
            title_terms = set(tokenize(document.title))
            overlap = len(query_terms & title_terms) / len(query_terms)
            scores[index] *= (1 + _TITLE_BOOST * overlap) * _KIND_WEIGHT.get(
                document.kind, 1.0
            )

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        return [Hit(self.documents[i], score) for i, score in ranked]


class EmbeddingIndex:
    """Cosine similarity over pre-computed document vectors."""

    def __init__(self, documents: list[Document], vectors: dict[str, list[float]]) -> None:
        self.by_id = {d.doc_id: d for d in documents}
        self.doc_ids = [d for d in vectors if d in self.by_id]
        self.vectors = [vectors[d] for d in self.doc_ids]
        self.norms = [math.sqrt(sum(v * v for v in vec)) or 1.0 for vec in self.vectors]

    def search(self, query_vector: list[float], limit: int = 6) -> list[Hit]:
        query_norm = math.sqrt(sum(v * v for v in query_vector)) or 1.0
        scored: list[tuple[float, str]] = []
        for doc_id, vector, norm in zip(self.doc_ids, self.vectors, self.norms):
            dot = sum(a * b for a, b in zip(query_vector, vector))
            scored.append((dot / (query_norm * norm), doc_id))
        scored.sort(reverse=True)
        return [Hit(self.by_id[doc_id], score) for score, doc_id in scored[:limit]]


class Retriever:
    def __init__(self) -> None:
        self.documents = build_documents()
        self.keyword = KeywordIndex(self.documents)
        self.embeddings: EmbeddingIndex | None = None

        if INDEX_PATH.exists():
            try:
                with INDEX_PATH.open(encoding="utf-8") as f:
                    payload = json.load(f)
                self.embeddings = EmbeddingIndex(self.documents, payload["vectors"])
                print(f"Embedding index loaded: {len(self.embeddings.doc_ids)} vectors")
            except (json.JSONDecodeError, KeyError, OSError) as exc:
                print(f"Warning: embedding index unusable ({exc}); keyword search only")

    @property
    def mode(self) -> str:
        return "hybrid" if self.embeddings else "keyword"

    def search(
        self,
        query: str,
        limit: int = 6,
        query_vector: list[float] | None = None,
    ) -> list[Hit]:
        keyword_hits = self.keyword.search(query, limit=limit * 2)

        if not (self.embeddings and query_vector):
            return keyword_hits[:limit]

        vector_hits = self.embeddings.search(query_vector, limit=limit * 2)

        # Reciprocal rank fusion — combines the two rankings without needing the
        # score scales to be comparable.
        fused: dict[str, float] = {}
        documents: dict[str, Document] = {}
        for rank, hit in enumerate(keyword_hits):
            fused[hit.document.doc_id] = fused.get(hit.document.doc_id, 0.0) + 1 / (60 + rank)
            documents[hit.document.doc_id] = hit.document
        for rank, hit in enumerate(vector_hits):
            fused[hit.document.doc_id] = fused.get(hit.document.doc_id, 0.0) + 1 / (60 + rank)
            documents[hit.document.doc_id] = hit.document

        ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        return [Hit(documents[doc_id], score) for doc_id, score in ranked]

    def by_slug_or_title(self, needle: str) -> Document | None:
        target = (needle or "").strip().lower()
        if not target:
            return None
        for document in self.documents:
            if document.kind != "package":
                continue
            if target in (document.title.lower(), (document.meta.get("slug") or "").lower()):
                return document
        for document in self.documents:
            if document.kind == "package" and target in document.title.lower():
                return document
        return None


@lru_cache(maxsize=1)
def get_retriever() -> Retriever:
    return Retriever()


SMOKE_QUERIES = (
    "full body checkup price",
    "thyroid test cost",
    "do I need to fast before the test",
    "what time does support open",
    "hair loss which test",
    "how do I get my report",
    "diabetes package",
    "is home collection free",
)


if __name__ == "__main__":
    retriever = get_retriever()
    print(f"{len(retriever.documents)} documents, mode={retriever.mode}\n")
    for smoke_query in SMOKE_QUERIES:
        print(f"Q: {smoke_query}")
        for hit in retriever.search(smoke_query, limit=3):
            print(f"   [{hit.document.kind:8}] {hit.document.title[:70]}")
        print()
