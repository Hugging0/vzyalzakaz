from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import make_engine
from app.models import (
    Base,
    ClassificationMethod,
    ContentCategory,
    OpportunityStatus,
    SemanticRepresentation,
    TelegramUser,
    UserOpportunity,
)
from app.schemas import RawOpportunity
from app.services.pipeline import OpportunityPipeline


@pytest.mark.asyncio
async def test_pipeline_merges_content_duplicates(settings, profile):
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    pipeline = OpportunityPipeline(settings)
    first = RawOpportunity(
        source="channel_a",
        source_type="telegram",
        external_id="1",
        title="Python automation",
        description="Python FastAPI automation project",
        raw_text="Python FastAPI automation project",
        published_at=datetime.now(UTC),
    )
    second = first.model_copy(update={"source": "channel_b", "external_id": "2"})
    async with session_factory() as session:
        created = await pipeline.process(session, first)
        merged = await pipeline.process(session, second)
    assert created.created
    assert not merged.created
    assert merged.merged
    assert merged.opportunity.id == created.opportunity.id
    await engine.dispose()


@pytest.mark.asyncio
async def test_pipeline_does_not_filter_by_owner_relevance(settings, profile):
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    pipeline = OpportunityPipeline(settings)
    raw = RawOpportunity(
        source="x", source_type="web", external_id="1", title="Chef", raw_text="Restaurant chef"
    )
    async with session_factory() as session:
        result = await pipeline.process(session, raw)
    assert result.opportunity.status == OpportunityStatus.NEW
    assert not hasattr(result.opportunity, "prefilter_score")
    assert not hasattr(result.opportunity, "final_score")
    await engine.dispose()


@pytest.mark.asyncio
async def test_pipeline_rejects_candidate_content_before_analyzer(settings, profile):
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    pipeline = OpportunityPipeline(settings)
    original_extract = pipeline.fact_extractor.extract
    pipeline.fact_extractor.extract = AsyncMock(wraps=original_extract)
    raw = RawOpportunity(
        source="telegram_candidates",
        source_type="telegram",
        external_id="candidate-1",
        title="Senior Python engineer",
        raw_text=(
            "Senior Python engineer, 6 years experience. FastAPI, PostgreSQL, Docker, AI. "
            "Open to work and available immediately. Portfolio and GitHub in profile."
        ),
    )

    async with session_factory() as session:
        result = await pipeline.process(session, raw)

    assert result.opportunity.status == OpportunityStatus.FILTERED
    assert result.opportunity.content_category == ContentCategory.JOB_SEEKER
    assert result.opportunity.classification_confidence >= 0.82
    assert result.opportunity.classification_method == ClassificationMethod.DETERMINISTIC
    assert not hasattr(result.opportunity, "prefilter_score")
    assert pipeline.fact_extractor.extract.await_args.kwargs["allow_llm"] is False
    await engine.dispose()


@pytest.mark.asyncio
async def test_pipeline_persists_unknown_without_recommending_globally(settings, profile):
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    pipeline = OpportunityPipeline(settings)
    raw = RawOpportunity(
        source="telegram_mixed",
        source_type="telegram",
        external_id="unknown-1",
        raw_text="Python FastAPI React automation. Details in DM.",
    )

    async with session_factory() as session:
        result = await pipeline.process(session, raw)

    assert result.opportunity.status == OpportunityStatus.NEW
    assert result.opportunity.content_category == ContentCategory.UNKNOWN
    assert "semantic:unavailable" in result.opportunity.classification_reasons
    assert result.opportunity.facts_version == "facts-v2"
    assert not hasattr(result.opportunity, "final_score")
    await engine.dispose()


@pytest.mark.asyncio
async def test_content_duplicate_is_classified_once(settings, profile):
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    pipeline = OpportunityPipeline(settings)
    original_classify = pipeline.classifier.classify
    pipeline.classifier.classify = AsyncMock(wraps=original_classify)
    first = RawOpportunity(
        source="channel_a",
        source_type="telegram",
        external_id="demand-1",
        raw_text="Looking for a Python developer for a paid project",
    )
    second = first.model_copy(update={"source": "channel_b", "external_id": "demand-2"})

    async with session_factory() as session:
        await pipeline.process(session, first)
        merged = await pipeline.process(session, second)

    assert merged.merged
    assert pipeline.classifier.classify.await_count == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_global_ingestion_is_candidate_neutral(settings, profile):
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    pipeline = OpportunityPipeline(settings)
    python_job = RawOpportunity(
        source="neutral",
        source_type="web",
        external_id="python",
        raw_text="Looking for a Python developer for a paid remote project",
        budget_max=1_000,
        currency="RUB",
    )
    figma_job = python_job.model_copy(
        update={
            "external_id": "figma",
            "raw_text": "Looking for a Figma designer for a paid remote project",
        }
    )
    async with session_factory() as session:
        first = await pipeline.process(session, python_job)
        second = await pipeline.process(session, figma_job)

    assert first.opportunity.status == OpportunityStatus.NEW
    assert second.opportunity.status == OpportunityStatus.NEW
    assert not hasattr(first.opportunity, "prefilter_score")
    assert not hasattr(second.opportunity, "prefilter_score")
    assert first.opportunity.facts["skills"] != second.opportunity.facts["skills"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_edited_opportunity_invalidates_semantics_and_only_pending_matches(settings, profile):
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    pipeline = OpportunityPipeline(settings)
    original = RawOpportunity(
        source="edit-test",
        source_type="web",
        external_id="same-id",
        title="Python API",
        raw_text="Looking for Python API developer",
        edited_at=datetime(2026, 9, 3, 10, tzinfo=UTC),
    )
    async with session_factory() as session:
        opportunity = (await pipeline.process(session, original)).opportunity
        first = TelegramUser(telegram_user_id=8001, profile=profile.model_dump(), portfolio=[])
        second = TelegramUser(telegram_user_id=8002, profile=profile.model_dump(), portfolio=[])
        session.add_all([first, second])
        await session.flush()
        pending = UserOpportunity(user_id=first.id, opportunity_id=opportunity.id)
        historical = UserOpportunity(
            user_id=second.id,
            opportunity_id=opportunity.id,
            status=OpportunityStatus.APPROVED,
            proposal="Keep this proposal",
        )
        session.add_all(
            [
                pending,
                historical,
                SemanticRepresentation(
                    entity_type="opportunity",
                    entity_key=str(opportunity.id),
                    input_hash="old",
                    provider="test",
                    model="test",
                    dimensions=2,
                    vector=[1.0, 0.0],
                ),
            ]
        )
        await session.commit()
        edited = original.model_copy(
            update={
                "title": "Django API",
                "raw_text": "Looking for Django API developer",
                "edited_at": datetime(2026, 9, 3, 11, tzinfo=UTC),
            }
        )
        result = await pipeline.process(session, edited)
        matches = (await session.scalars(select(UserOpportunity))).all()
        cache_count = await session.scalar(
            select(func.count()).select_from(SemanticRepresentation)
        )

    assert result.updated
    assert result.opportunity.title == "Django API"
    assert cache_count == 0
    assert [(item.status, item.proposal) for item in matches] == [
        (OpportunityStatus.APPROVED, "Keep this proposal")
    ]
    await engine.dispose()
