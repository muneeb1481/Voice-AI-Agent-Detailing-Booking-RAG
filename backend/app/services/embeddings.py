"""Embedding provider behind a tiny interface.

Without OPENAI_API_KEY the deterministic hash embedder is used, so the whole stack
(upload -> chunk -> embed -> retrieve) runs in tests and local dev with no network.
"""
from __future__ import annotations

import hashlib
import math
from typing import Protocol

from app.config import get_settings

settings = get_settings()


class Embedder(Protocol):
    # Relevance floor is a property of the embedding space, not a global constant:
    # real semantic embeddings score far higher than the hashing stand-in.
    min_score: float

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbedder:
    """Deterministic bag-of-words hashing. Not semantic — a stand-in, not a substitute."""

    min_score = 0.04

    def __init__(self, dim: int) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode()).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class OpenAIEmbedder:
    min_score = 0.25

    def __init__(self, api_key: str, model: str, dim: int) -> None:
        from openai import OpenAI  # noqa: PLC0415

        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self.client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in resp.data]


def get_embedder() -> Embedder:
    if settings.openai_api_key:
        return OpenAIEmbedder(
            settings.openai_api_key, settings.embedding_model, settings.embedding_dim
        )
    return HashEmbedder(settings.embedding_dim)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
