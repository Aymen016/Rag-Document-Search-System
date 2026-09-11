"""
Embedding provider abstraction. Default is fully local and free: a
sentence-transformers model runs on CPU, no API key, no per-call cost.

Swap EMBEDDING_PROVIDER in .env to "voyage" or "openai" later if you want to
compare quality against a hosted model (the plan notes Voyage is stronger on
technical/code content) — everything downstream (search.py) only calls
.embed(texts), so it doesn't care which provider is behind it.
"""
from __future__ import annotations

from functools import lru_cache

import config


class Embedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]


class LocalEmbedder(Embedder):
    """Free, no API key. Downloads the model once from Hugging Face on first
    use (needs network for that one-time download; after that it's offline)."""

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        # normalize_embeddings=True so cosine similarity == dot product,
        # which is what Chroma's default "cosine" space expects.
        vectors = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=32,
        )
        return vectors.tolist()


class VoyageEmbedder(Embedder):
    def __init__(self, model_name: str = "voyage-3"):
        import voyageai

        if not config.VOYAGE_API_KEY:
            raise RuntimeError("VOYAGE_API_KEY not set in .env")
        self.client = voyageai.Client(api_key=config.VOYAGE_API_KEY)
        self.model_name = model_name

    def embed(self, texts: list[str]) -> list[list[float]]:
        result = self.client.embed(texts, model=self.model_name, input_type="document")
        return result.embeddings


class OpenAIEmbedder(Embedder):
    def __init__(self, model_name: str = "text-embedding-3-small"):
        from openai import OpenAI

        if not config.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not set in .env")
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)
        self.model_name = model_name

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self.client.embeddings.create(input=texts, model=self.model_name)
        return [d.embedding for d in resp.data]


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """Cached so the (possibly large) local model is loaded once per process,
    not once per request."""
    provider = config.EMBEDDING_PROVIDER
    if provider == "local":
        return LocalEmbedder(config.LOCAL_EMBEDDING_MODEL)
    if provider == "voyage":
        return VoyageEmbedder()
    if provider == "openai":
        return OpenAIEmbedder()
    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {provider!r}")
