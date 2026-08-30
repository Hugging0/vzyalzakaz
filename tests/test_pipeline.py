from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import make_engine
from app.models import Base, OpportunityStatus
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
