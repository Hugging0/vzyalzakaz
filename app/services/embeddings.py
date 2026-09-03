from __future__ import annotations

import math
from typing import Protocol

import httpx

from app.config import AppSettings


class EmbeddingError(RuntimeError):
    pass


class EmbeddingProvider(Protocol):
    name: str
    model: str
    available: bool

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class DisabledEmbeddingProvider:
    name = "disabled"
    model = "lexical-fallback-v2"
    available = False

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingError("embedding provider is disabled")


class OpenAICompatibleEmbeddingProvider:
    name = "openai_compatible"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        base_url: str,
        timeout_seconds: float,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    @property
    def available(self) -> bool:
        return bool(self.api_key and self.model and self.base_url)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.available:
            raise EmbeddingError("embedding provider is not configured")
        if not texts or any(not text.strip() for text in texts):
            raise EmbeddingError("embedding input must contain non-empty text")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/embeddings",
                    headers=headers,
                    json={"model": self.model, "input": texts, "encoding_format": "float"},
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EmbeddingError("embedding request failed") from exc
        data = payload.get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            raise EmbeddingError("embedding response has invalid item count")
        ordered = sorted(data, key=lambda item: item.get("index", -1))
        vectors = [item.get("embedding") for item in ordered]
        return validate_vectors(vectors, expected=len(texts))


def validate_vectors(vectors: object, *, expected: int) -> list[list[float]]:
    if not isinstance(vectors, list) or len(vectors) != expected:
        raise EmbeddingError("embedding response shape mismatch")
    normalized: list[list[float]] = []
    dimensions: int | None = None
    for vector in vectors:
        if not isinstance(vector, list) or not vector:
            raise EmbeddingError("embedding vector is empty")
        try:
            values = [float(value) for value in vector]
        except (TypeError, ValueError) as exc:
            raise EmbeddingError("embedding vector is not numeric") from exc
        if any(not math.isfinite(value) for value in values):
            raise EmbeddingError("embedding vector contains a non-finite value")
        norm = math.sqrt(sum(value * value for value in values))
        if norm <= 1e-12:
            raise EmbeddingError("embedding vector has zero norm")
        if dimensions is None:
            dimensions = len(values)
        elif dimensions != len(values):
            raise EmbeddingError("embedding vector dimensions differ")
        normalized.append([value / norm for value in values])
    return normalized


def build_embedding_provider(settings: AppSettings) -> EmbeddingProvider:
    if settings.embedding_provider == "openai_compatible":
        return OpenAICompatibleEmbeddingProvider(
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
            base_url=settings.embedding_base_url,
            timeout_seconds=settings.embedding_timeout_seconds,
        )
    return DisabledEmbeddingProvider()
