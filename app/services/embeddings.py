from __future__ import annotations

import math
from typing import Literal, Protocol

import httpx

from app.config import AppSettings


class EmbeddingError(RuntimeError):
    pass


EmbeddingPurpose = Literal["document", "query"]


class EmbeddingProvider(Protocol):
    name: str
    model: str
    available: bool

    def model_for(self, purpose: EmbeddingPurpose) -> str: ...

    async def embed(
        self, texts: list[str], *, purpose: EmbeddingPurpose = "document"
    ) -> list[list[float]]: ...


class DisabledEmbeddingProvider:
    name = "disabled"
    model = "lexical-fallback-v2"
    available = False

    def model_for(self, purpose: EmbeddingPurpose) -> str:
        return self.model

    async def embed(
        self, texts: list[str], *, purpose: EmbeddingPurpose = "document"
    ) -> list[list[float]]:
        raise EmbeddingError("embedding provider is disabled")


class TimewebYandexEmbeddingProvider:
    name = "timeweb_yandex"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        query_model: str,
        base_url: str,
        timeout_seconds: float,
    ):
        self.api_key = api_key
        self.model = model
        self.query_model = query_model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    @property
    def available(self) -> bool:
        return bool(self.api_key and self.model and self.query_model and self.base_url)

    def model_for(self, purpose: EmbeddingPurpose) -> str:
        return self.query_model if purpose == "query" else self.model

    async def embed(
        self, texts: list[str], *, purpose: EmbeddingPurpose = "document"
    ) -> list[list[float]]:
        if not self.available:
            raise EmbeddingError("embedding provider is not configured")
        if not texts or any(not text.strip() for text in texts):
            raise EmbeddingError("embedding input must contain non-empty text")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        vectors = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                # Yandex via Timeweb accepts a single string per request. Array
                # inputs return 503, even for two short texts. Keep batch ordering
                # here and return only after every response has been validated.
                for text in texts:
                    response = await client.post(
                        f"{self.base_url}/embeddings",
                        headers=headers,
                        json={"model": self.model_for(purpose), "input": text},
                    )
                    response.raise_for_status()
                    payload = response.json()
                    data = payload.get("data") if isinstance(payload, dict) else None
                    if (
                        not isinstance(data, list)
                        or len(data) != 1
                        or not isinstance(data[0], dict)
                    ):
                        raise EmbeddingError("embedding response has invalid item count")
                    vectors.append(data[0].get("embedding"))
        except (httpx.HTTPError, ValueError) as exc:
            raise EmbeddingError("embedding request failed") from exc
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
    if settings.embedding_provider == "timeweb_yandex":
        return TimewebYandexEmbeddingProvider(
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
            query_model=settings.embedding_query_model,
            base_url=settings.embedding_base_url,
            timeout_seconds=settings.embedding_timeout_seconds,
        )
    return DisabledEmbeddingProvider()
