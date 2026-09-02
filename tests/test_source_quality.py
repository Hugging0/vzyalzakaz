from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import make_engine
from app.models import Base, ContentCategory, Opportunity, SourceOccurrence
from app.services.source_quality import source_quality_snapshots


def opportunity(external_id: str, category: ContentCategory) -> Opportunity:
    return Opportunity(
        source="channel_a",
        source_type="telegram",
        external_id=external_id,
        title=external_id,
        description=external_id,
        raw_text=external_id,
        normalized_hash=external_id.ljust(64, "0"),
        content_category=category,
    )


@pytest.mark.asyncio
async def test_source_quality_uses_occurrences_and_category_distribution(settings) -> None:
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        job = opportunity("job", ContentCategory.JOB)
        resume = opportunity("resume", ContentCategory.RESUME)
        advertisement = opportunity("advertisement", ContentCategory.ADVERTISEMENT)
        session.add_all([job, resume, advertisement])
        await session.flush()
        session.add_all(
            [
                SourceOccurrence(opportunity_id=job.id, source="channel_a", external_id="1"),
                SourceOccurrence(opportunity_id=resume.id, source="channel_a", external_id="2"),
                SourceOccurrence(opportunity_id=advertisement.id, source="channel_a", external_id="3"),
                SourceOccurrence(opportunity_id=job.id, source="channel_b", external_id="4"),
            ]
        )
        await session.commit()

        snapshots = await source_quality_snapshots(session)

    by_source = {snapshot.source: snapshot for snapshot in snapshots}
    assert by_source["channel_a"].total == 3
    assert by_source["channel_a"].categories == {"advertisement": 1, "job": 1, "resume": 1}
    assert by_source["channel_a"].opportunity_share == pytest.approx(1 / 3, abs=0.0001)
    assert by_source["channel_b"].opportunity_share == 1
    await engine.dispose()
