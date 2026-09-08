from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import make_engine
from app.models import Base, ContentCategory, Opportunity, SemanticRepresentation, TelegramUser
from app.schemas import OpportunityFacts
from app.services.embeddings import EmbeddingError
from app.services.retrieval import CandidateRetriever, lexical_similarity


class SemanticTestProvider:
    name = "semantic_test"
    model = "meaning-v1"
    available = True

    def __init__(self):
        self.calls = 0
        self.fail = False
        self.invalid = False

    def model_for(self, purpose):
        return self.model

    async def embed(self, texts: list[str], *, purpose="document") -> list[list[float]]:
        self.calls += 1
        if self.fail:
            raise EmbeddingError("outage")
        if self.invalid:
            return [[float("nan"), 1.0] for _ in texts]
        vectors = []
        for text in texts:
            lowered = text.lower()
            if any(value in lowered for value in ("cobol", "z/os", "mainframe")):
                vectors.append([1.0, 0.0, 0.0])
            elif any(value in lowered for value in ("figma", "прототип", "designer")):
                vectors.append([0.0, 1.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0])
        return vectors


def make_opportunity(external_id: str, title: str) -> tuple[Opportunity, OpportunityFacts]:
    opportunity = Opportunity(
        source="test",
        source_type="web",
        external_id=external_id,
        title=title,
        description=title,
        raw_text=title,
        normalized_hash=external_id.zfill(64),
        content_category=ContentCategory.PROJECT,
        published_at=datetime.now(UTC),
    )
    facts = OpportunityFacts(title=title, category="project", source_confidence=0.9)
    return opportunity, facts


@pytest.mark.asyncio
async def test_embedding_retrieval_handles_meaning_without_shared_aliases(settings, profile):
    engine = make_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    provider = SemanticTestProvider()
    retriever = CandidateRetriever(settings, provider)
    profile.candidate.about = "Maintains COBOL workloads"
    profile.candidate.skills = ["COBOL"]
    relevant = make_opportunity("1", "Modernize z/OS batch processing")
    irrelevant = make_opportunity("2", "Create a Figma prototype")
    async with factory() as session:
        user = TelegramUser(telegram_user_id=1, profile=profile.model_dump(), portfolio=[])
        session.add_all([user, relevant[0], irrelevant[0]])
        await session.flush()
        ranked = await retriever.retrieve(session, user, profile, [], [irrelevant, relevant], top_k=1)
        await session.commit()

    assert ranked[0].opportunity.external_id == "1"
    assert ranked[0].embedding_score == 100
    assert not ranked[0].fallback_used
    await engine.dispose()


@pytest.mark.asyncio
async def test_embeddings_are_cached_and_profile_hash_invalidates_only_profile(settings, profile):
    engine = make_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    provider = SemanticTestProvider()
    retriever = CandidateRetriever(settings, provider)
    candidate = make_opportunity("3", "Modernize z/OS batch processing")
    profile.candidate.skills = ["COBOL"]
    async with factory() as session:
        user = TelegramUser(telegram_user_id=3, profile=profile.model_dump(), portfolio=[])
        session.add_all([user, candidate[0]])
        await session.flush()
        await retriever.retrieve(session, user, profile, [], [candidate])
        first_calls = provider.calls
        await retriever.retrieve(session, user, profile, [], [candidate])
        assert provider.calls == first_calls
        original_facts = candidate[1].model_dump()
        profile.candidate.about = "COBOL and mainframe operations"
        await retriever.retrieve(session, user, profile, [], [candidate])
        opportunity_cache_count = await session.scalar(
            select(func.count())
            .select_from(SemanticRepresentation)
            .where(SemanticRepresentation.entity_type == "opportunity")
        )
        assert provider.calls == first_calls + 1
        assert opportunity_cache_count == 1
        assert candidate[1].model_dump() == original_facts
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["outage", "invalid"])
async def test_embedding_failures_use_fallback_without_corrupting_cache(settings, profile, failure):
    engine = make_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    provider = SemanticTestProvider()
    provider.fail = failure == "outage"
    provider.invalid = failure == "invalid"
    retriever = CandidateRetriever(settings, provider)
    candidate = make_opportunity("4", "COBOL mainframe maintenance")
    profile.candidate.skills = ["COBOL"]
    async with factory() as session:
        user = TelegramUser(telegram_user_id=4, profile=profile.model_dump(), portfolio=[])
        session.add_all([user, candidate[0]])
        await session.flush()
        ranked = await retriever.retrieve(session, user, profile, [], [candidate])
        await session.commit()
        cache_count = await session.scalar(select(func.count()).select_from(SemanticRepresentation))

    assert ranked[0].fallback_used
    assert cache_count == 0
    await engine.dispose()


def test_common_vacancy_words_do_not_create_false_similarity():
    score = lexical_similarity(
        "Ищу проекты и задачи, специалист с опытом работы",
        "Нужен специалист на проект, описание задачи и условий работы",
    )

    assert score < 5


@pytest.mark.asyncio
async def test_query_and_document_models_are_routed_and_cached_separately(settings, profile):
    class PairedProvider(SemanticTestProvider):
        query_model = "query-v1"

        def __init__(self):
            super().__init__()
            self.purposes = []

        def model_for(self, purpose):
            return self.query_model if purpose == "query" else "doc-v1"

        async def embed(self, texts, *, purpose="document"):
            self.purposes.append(purpose)
            return await super().embed(texts, purpose=purpose)

    engine = make_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    provider = PairedProvider()
    retriever = CandidateRetriever(settings, provider)
    candidate = make_opportunity("paired", "COBOL mainframe maintenance")
    async with factory() as session:
        user = TelegramUser(telegram_user_id=55, profile=profile.model_dump(), portfolio=[])
        session.add_all([user, candidate[0]])
        await session.flush()
        await retriever.retrieve(session, user, profile, [], [candidate])
        assert provider.purposes == ["query", "document"]
        await retriever.retrieve(session, user, profile, [], [candidate])
        assert provider.purposes == ["query", "document"]
        provider.query_model = "query-v2"
        await retriever.retrieve(session, user, profile, [], [candidate])
        assert provider.purposes == ["query", "document", "query"]
        cache = (await session.scalars(select(SemanticRepresentation))).all()
        assert {(row.entity_type, row.model) for row in cache} == {
            ("profile", "query-v1"),
            ("profile", "query-v2"),
            ("opportunity", "doc-v1"),
        }
    await engine.dispose()


@pytest.mark.asyncio
async def test_cold_corpus_limits_api_work_without_dropping_uncached_orders(settings, profile):
    engine = make_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    provider = SemanticTestProvider()
    retriever = CandidateRetriever(settings, provider)
    candidates = [make_opportunity(str(i), "Create a Figma prototype") for i in range(6)]
    candidates[-1][0].source = "quiet"
    async with factory() as session:
        user = TelegramUser(telegram_user_id=99, profile=profile.model_dump(), portfolio=[])
        session.add_all([user, *[o for o, _ in candidates]])
        await session.flush()
        results = await retriever.retrieve(
            session, user, profile, [], candidates, top_k=6, max_new_embeddings=2
        )
        assert len(results) == 6
        assert sum(not r.fallback_used for r in results) == 2
        assert not next(r for r in results if r.opportunity.source == "quiet").fallback_used
        rows = (
            await session.scalars(
                select(SemanticRepresentation).where(SemanticRepresentation.entity_type == "opportunity")
            )
        ).all()
        assert len(rows) == 2
        calls = provider.calls
        results = await retriever.retrieve(
            session, user, profile, [], candidates, top_k=6, max_new_embeddings=0
        )
        assert provider.calls == calls
        assert sum(not r.fallback_used for r in results) == 2
    await engine.dispose()
