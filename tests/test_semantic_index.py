from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import make_engine
from app.models import Base, ContentCategory, Opportunity, SemanticRepresentation
from app.services.embeddings import EmbeddingError
from app.services.recommendations import RecommendationService
from app.services.retrieval import CandidateRetriever
from app.services.semantic_index import index_active_corpus


class Provider:
    available = True
    name = "test"
    model = "test"

    def __init__(self):
        self.calls = 0

    def model_for(self, purpose):
        return self.model

    async def embed(self, texts, *, purpose="document"):
        self.calls += 1
        if any("poison" in text for text in texts):
            raise EmbeddingError("upstream rejected this document")
        return [[1.0, 0.0] for text in texts]


@pytest.mark.asyncio
async def test_one_bad_document_does_not_lose_successes_or_repeat_paid_work(settings, profile):
    engine = make_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    provider = Provider()
    service = RecommendationService(settings, profile, [], CandidateRetriever(settings, provider))
    async with factory() as session:
        for index, title in enumerate(["React form", "poison", "Edit a video"]):
            session.add(
                Opportunity(
                    source=f"source{index}",
                    source_type="web",
                    external_id=str(index),
                    title=title,
                    description=title,
                    raw_text=title,
                    normalized_hash=str(index).zfill(64),
                    content_category=ContentCategory.PROJECT,
                    published_at=datetime.now(UTC),
                    facts={"title": title},
                    facts_version="facts-v3",
                )
            )
        await session.commit()
    first = await index_active_corpus(factory, service)
    assert first["indexed"] == 2 and first["failed"] == 1 and first["attempted"] == 3
    assert provider.calls == 3
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(SemanticRepresentation)) == 2
    second = await index_active_corpus(factory, service)
    assert second["indexed"] == 0 and second["attempted"] == 0 and second["cache_hits"] == 2
    assert provider.calls == 3
    await engine.dispose()
