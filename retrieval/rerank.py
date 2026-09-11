"""
Reranking (Phase 4, step 3 of the plan): retrieve top-25 candidates cheaply
via hybrid search, then rerank down to top-5 with a model that actually reads
query+document together. Usually the single biggest quality jump for the
least code.

Default is local and free (a cross-encoder via sentence-transformers).
Swap RERANK_PROVIDER to "cohere" in .env if you want to compare.
"""
from __future__ import annotations

from functools import lru_cache

import config


class Reranker:
    def rerank(self, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        """candidates: list of dicts each with at least a 'text' key.
        Returns the same dicts, trimmed to top_k, sorted by rerank_score desc,
        with a 'rerank_score' key added."""
        raise NotImplementedError


class LocalReranker(Reranker):
    def __init__(self, model_name: str):
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        if not candidates:
            return []
        pairs = [(query, c["text"]) for c in candidates]
        scores = self.model.predict(pairs)
        for c, s in zip(candidates, scores):
            c["rerank_score"] = float(s)
        candidates.sort(key=lambda c: c["rerank_score"], reverse=True)
        return candidates[:top_k]


class CohereReranker(Reranker):
    def __init__(self, model_name: str = "rerank-english-v3.0"):
        import cohere

        if not config.COHERE_API_KEY:
            raise RuntimeError("COHERE_API_KEY not set in .env")
        self.client = cohere.Client(config.COHERE_API_KEY)
        self.model_name = model_name

    def rerank(self, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        if not candidates:
            return []
        docs = [c["text"] for c in candidates]
        result = self.client.rerank(
            query=query, documents=docs, top_n=top_k, model=self.model_name
        )
        reranked = []
        for r in result.results:
            c = dict(candidates[r.index])
            c["rerank_score"] = float(r.relevance_score)
            reranked.append(c)
        return reranked


@lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    provider = config.RERANK_PROVIDER
    if provider == "local":
        return LocalReranker(config.LOCAL_RERANK_MODEL)
    if provider == "cohere":
        return CohereReranker()
    raise ValueError(f"Unknown RERANK_PROVIDER: {provider!r}")
