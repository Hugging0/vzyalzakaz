from __future__ import annotations

import hashlib
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import CandidateProfile, PortfolioProject
from app.models import Opportunity, SemanticRepresentation, TelegramUser
from app.schemas import OpportunityFacts
from app.services.embeddings import (
    EmbeddingError,
    EmbeddingProvider,
    build_embedding_provider,
    validate_vectors,
)
from app.services.normalizer import normalize_text

logger = logging.getLogger(__name__)
RETRIEVAL_VERSION = "retrieval-v2"

# This compact ontology is used only during provider outages or when embeddings are disabled.
# It is deliberately separated from the primary semantic retrieval path.
FALLBACK_CAPABILITY_GROUPS = {
    "backend": ("backend", "server side", "серверн", "api", "rest", "django", "fastapi", "flask"),
    "frontend": ("frontend", "client side", "интерфейс", "react", "vue", "next.js", "typescript"),
    "design": (
        "design",
        "дизайн",
        "ui",
        "ux",
        "figma",
        "айдентик",
        "branding",
        "user experience",
        "пользовательский опыт",
    ),
    "marketing": ("marketing", "маркетинг", "smm", "соцсет", "таргет", "seo", "контент"),
    "video": ("video", "видео", "монтаж", "motion", "моушн", "reels", "after effects"),
    "content": ("copy", "копирай", "редактор", "статья", "текст", "сценар"),
    "automation": ("automation", "автоматизац", "интеграц", "workflow", "n8n", "make", "zapier"),
    "data": ("data", "данн", "аналит", "sql", "etl", "bi", "machine learning"),
}
STOP_WORDS = {
    "для", "или", "это", "как", "the", "and", "with", "from", "нужно", "ищем", "работа",
    "проект", "задача", "требуется", "looking", "project", "developer", "специалист",
    "проекты", "проектов", "задачи", "задач", "опыт", "опытом", "работы", "условия",
    "условий", "описание", "ищу",
}


@dataclass(frozen=True, slots=True)
class RetrievalCandidate:
    opportunity: Opportunity
    facts: OpportunityFacts
    score: float
    embedding_score: float | None
    lexical_score: float
    fallback_used: bool


class CandidateRetriever:
    def __init__(self, settings, provider: EmbeddingProvider | None = None):
        self.settings = settings
        self.provider = provider or build_embedding_provider(settings)

    async def retrieve(
        self,
        session: AsyncSession,
        user: TelegramUser,
        profile: CandidateProfile,
        portfolio: list[PortfolioProject],
        candidates: list[tuple[Opportunity, OpportunityFacts]],
        *,
        top_k: int | None = None,
    ) -> list[RetrievalCandidate]:
        if not candidates:
            return []
        specialties = (user.profile or {}).get("ui", {}).get("specialties", [])
        profile_text = profile_retrieval_text(profile, portfolio, specialties=specialties)
        opportunity_texts = [opportunity_retrieval_text(facts) for _, facts in candidates]
        lexical = [lexical_similarity(profile_text, text) for text in opportunity_texts]
        fallback_used = True
        embedding_scores: list[float | None] = [None] * len(candidates)
        cache_hits = cache_misses = 0
        if self.provider.available:
            try:
                async with session.begin_nested():
                    profile_vector, hit = await self._vector(
                        session, "profile", str(user.id), profile_text
                    )
                    cache_hits += int(hit)
                    cache_misses += int(not hit)
                    vectors, hits = await self._opportunity_vectors(
                        session,
                        [str(opportunity.id) for opportunity, _ in candidates],
                        opportunity_texts,
                        [opportunity.facts_version or "unversioned" for opportunity, _ in candidates],
                    )
                    cache_hits += hits
                    cache_misses += len(vectors) - hits
                    embedding_scores = [
                        round(cosine(profile_vector, vector) * 100, 2) for vector in vectors
                    ]
                fallback_used = False
            except EmbeddingError:
                logger.warning("retrieval_embedding_fallback provider=%s", self.provider.name, exc_info=True)
        results = []
        for (opportunity, facts), lexical_score, embedding_score in zip(
            candidates, lexical, embedding_scores, strict=True
        ):
            score = (
                lexical_score
                if embedding_score is None
                else embedding_score * 0.85 + lexical_score * 0.15
            )
            results.append(
                RetrievalCandidate(
                    opportunity=opportunity,
                    facts=facts,
                    score=round(score, 2),
                    embedding_score=embedding_score,
                    lexical_score=round(lexical_score, 2),
                    fallback_used=fallback_used,
                )
            )
        results.sort(key=lambda item: item.score, reverse=True)
        selected = results[: top_k or self.settings.matching_retrieval_top_k]
        logger.info(
            "recommendation_retrieval scanned=%d candidates=%d selected=%d provider=%s "
            "cache_hits=%d cache_misses=%d fallback=%s",
            len(candidates),
            len(results),
            len(selected),
            self.provider.name,
            cache_hits,
            cache_misses,
            fallback_used,
        )
        return selected

    async def _vector(
        self,
        session: AsyncSession,
        entity_type: str,
        entity_key: str,
        text: str,
    ) -> tuple[list[float], bool]:
        hashes = [text_hash(text)]
        cached = await self._cached(session, entity_type, [entity_key], hashes)
        if entity_key in cached:
            return cached[entity_key], True
        vectors = validate_vectors(await self.provider.embed([text]), expected=1)
        await self._persist_vectors(session, entity_type, [entity_key], hashes, vectors)
        return vectors[0], False

    async def _opportunity_vectors(
        self,
        session: AsyncSession,
        keys: list[str],
        texts: list[str],
        facts_versions: list[str],
    ) -> tuple[list[list[float]], int]:
        hashes = [
            text_hash(f"{facts_version}\0{text}")
            for facts_version, text in zip(facts_versions, texts, strict=True)
        ]
        cached = await self._cached(session, "opportunity", keys, hashes)
        missing_indices = [index for index, key in enumerate(keys) if key not in cached]
        generated: dict[str, list[float]] = {}
        batch_size = self.settings.embedding_batch_size
        # Validate every upstream batch before staging any cache writes. This prevents
        # partial or malformed provider responses from corrupting persisted vectors.
        for start in range(0, len(missing_indices), batch_size):
            batch_indices = missing_indices[start : start + batch_size]
            batch_vectors = validate_vectors(
                await self.provider.embed([texts[index] for index in batch_indices]),
                expected=len(batch_indices),
            )
            generated.update(
                {keys[index]: vector for index, vector in zip(batch_indices, batch_vectors, strict=True)}
            )
        if generated:
            generated_keys = [keys[index] for index in missing_indices]
            await self._persist_vectors(
                session,
                "opportunity",
                generated_keys,
                [hashes[index] for index in missing_indices],
                [generated[key] for key in generated_keys],
            )
        return [cached.get(key) or generated[key] for key in keys], len(cached)

    async def _cached(
        self,
        session: AsyncSession,
        entity_type: str,
        keys: list[str],
        hashes: list[str],
    ) -> dict[str, list[float]]:
        if not keys:
            return {}
        rows = (
            await session.scalars(
                select(SemanticRepresentation).where(
                    SemanticRepresentation.entity_type == entity_type,
                    SemanticRepresentation.entity_key.in_(keys),
                    SemanticRepresentation.provider == self.provider.name,
                    SemanticRepresentation.model == self.provider.model,
                )
            )
        ).all()
        expected = dict(zip(keys, hashes, strict=True))
        valid: dict[str, list[float]] = {}
        for row in rows:
            if row.input_hash != expected.get(row.entity_key) or row.dimensions != len(
                row.vector or []
            ):
                continue
            try:
                valid[row.entity_key] = validate_vectors([row.vector], expected=1)[0]
            except EmbeddingError:
                logger.warning(
                    "retrieval_cache_invalid entity_type=%s entity_key=%s",
                    entity_type,
                    row.entity_key,
                )
        return valid

    async def _persist_vectors(
        self,
        session: AsyncSession,
        entity_type: str,
        keys: list[str],
        hashes: list[str],
        vectors: list[list[float]],
    ) -> None:
        existing_rows = (
            await session.scalars(
                select(SemanticRepresentation).where(
                    SemanticRepresentation.entity_type == entity_type,
                    SemanticRepresentation.entity_key.in_(keys),
                    SemanticRepresentation.provider == self.provider.name,
                    SemanticRepresentation.model == self.provider.model,
                )
            )
        ).all()
        existing_by_key = {row.entity_key: row for row in existing_rows}
        for key, input_hash, vector in zip(keys, hashes, vectors, strict=True):
            existing = existing_by_key.get(key)
            if existing:
                existing.input_hash = input_hash
                existing.dimensions = len(vector)
                existing.vector = vector
            else:
                session.add(
                    SemanticRepresentation(
                        entity_type=entity_type,
                        entity_key=key,
                        input_hash=input_hash,
                        provider=self.provider.name,
                        model=self.provider.model,
                        dimensions=len(vector),
                        vector=vector,
                    )
                )
        await session.flush()


def profile_retrieval_text(
    profile: CandidateProfile,
    portfolio: list[PortfolioProject],
    *,
    specialties: list[str] | None = None,
) -> str:
    cases = [f"{item.title}. {item.description}. {' '.join(item.skills)}" for item in portfolio]
    return "\n".join(
        value
        for value in (
            profile.candidate.about,
            ", ".join(profile.candidate.skills),
            ", ".join(profile.candidate.secondary_skills),
            ", ".join(specialties or []),
            " | ".join(cases),
        )
        if value.strip()
    ) or "Profile has no described capabilities"


def opportunity_retrieval_text(facts: OpportunityFacts) -> str:
    return "\n".join(
        value
        for value in (
            facts.title,
            " ".join([*facts.skills, *facts.technologies]),
            " | ".join(facts.deliverables),
            facts.seniority or "",
        )
        if value.strip()
    )


def lexical_similarity(left: str, right: str) -> float:
    left_vector = _fallback_vector(left)
    right_vector = _fallback_vector(right)
    if not left_vector or not right_vector:
        return 0.0
    numerator = sum(value * right_vector.get(key, 0) for key, value in left_vector.items())
    left_norm = math.sqrt(sum(value * value for value in left_vector.values()))
    right_norm = math.sqrt(sum(value * value for value in right_vector.values()))
    return round(numerator / max(left_norm * right_norm, 1e-9) * 100, 2)


def fallback_concepts(text: str) -> set[str]:
    normalized = normalize_text(text)
    return {
        concept
        for concept, phrases in FALLBACK_CAPABILITY_GROUPS.items()
        if any(phrase in normalized for phrase in phrases)
    }


def cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        raise EmbeddingError("cached embedding dimensions differ")
    return max(0.0, min(1.0, sum(a * b for a, b in zip(left, right, strict=True))))


def text_hash(text: str) -> str:
    return hashlib.sha256(f"{RETRIEVAL_VERSION}\0{text}".encode()).hexdigest()


def _fallback_vector(text: str) -> Counter[str]:
    normalized = normalize_text(text)
    tokens = [
        token for token in re.findall(r"[a-zа-яё0-9+#.]{3,}", normalized) if token not in STOP_WORDS
    ]
    vector: Counter[str] = Counter(tokens)
    for token in tokens:
        if len(token) >= 5:
            vector.update(f"tri:{token[index:index + 3]}" for index in range(len(token) - 2))
    for concept in fallback_concepts(normalized):
        vector[f"concept:{concept}"] += 4
    return vector
