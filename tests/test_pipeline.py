from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import make_engine
from app.models import Base, ClassificationMethod, ContentCategory, OpportunityStatus
from app.schemas import RawOpportunity
from app.services.pipeline import OpportunityPipeline


@pytest.mark.asyncio
async def test_pipeline_merges_content_duplicates(settings, profile):
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    pipeline = OpportunityPipeline(settings, profile, settings.load_portfolio())
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
async def test_pipeline_filters_irrelevant_item(settings, profile):
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    pipeline = OpportunityPipeline(settings, profile, settings.load_portfolio())
    raw = RawOpportunity(
        source="x", source_type="web", external_id="1", title="Chef", raw_text="Restaurant chef"
    )
    async with session_factory() as session:
        result = await pipeline.process(session, raw)
    assert result.opportunity.status == OpportunityStatus.FILTERED
    await engine.dispose()


@pytest.mark.asyncio
async def test_pipeline_rejects_candidate_content_before_analyzer(settings, profile):
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    pipeline = OpportunityPipeline(settings, profile, settings.load_portfolio())
    pipeline.analyzer.analyze = AsyncMock()
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
    assert result.opportunity.prefilter_score is None
    pipeline.analyzer.analyze.assert_not_awaited()
    await engine.dispose()


@pytest.mark.asyncio
async def test_pipeline_fails_closed_when_intent_is_unknown(settings, profile):
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    pipeline = OpportunityPipeline(settings, profile, settings.load_portfolio())
    pipeline.analyzer.analyze = AsyncMock()
    raw = RawOpportunity(
        source="telegram_mixed",
        source_type="telegram",
        external_id="unknown-1",
        raw_text="Python FastAPI React automation. Details in DM.",
    )

    async with session_factory() as session:
        result = await pipeline.process(session, raw)

    assert result.opportunity.status == OpportunityStatus.FILTERED
    assert result.opportunity.content_category == ContentCategory.UNKNOWN
    assert "semantic:unavailable" in result.opportunity.classification_reasons
    pipeline.analyzer.analyze.assert_not_awaited()
    await engine.dispose()


@pytest.mark.asyncio
async def test_content_duplicate_is_classified_once(settings, profile):
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    pipeline = OpportunityPipeline(settings, profile, settings.load_portfolio())
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
