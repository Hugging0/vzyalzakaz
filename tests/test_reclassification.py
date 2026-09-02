from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import make_engine
from app.models import Base, ContentCategory, Opportunity, OpportunityStatus, TelegramUser, UserOpportunity
from app.reclassify_content import reclassify_legacy_rows


@pytest.mark.asyncio
async def test_legacy_supply_post_is_reclassified_as_global_reject(
    settings,
    profile,
    tmp_path,
) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'reclassification.db'}"
    local_settings = settings.model_copy(update={"database_url": database_url})
    engine = make_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        opportunity = Opportunity(
            source="telegram_candidates",
            source_type="telegram",
            external_id="legacy-candidate",
            title="Senior Python developer",
            description="Python FastAPI Docker. Open to work.",
            raw_text="Senior Python developer, 7 YOE. Open to work. My portfolio and GitHub.",
            normalized_hash="a" * 64,
        )
        user = TelegramUser(
            telegram_user_id=123,
            profile=profile.model_dump(),
            portfolio=[],
        )
        session.add_all([opportunity, user])
        await session.flush()
        match = UserOpportunity(
            user_id=user.id,
            opportunity_id=opportunity.id,
            prefilter_score=90,
            fit_score=90,
            money_score=50,
            win_score=70,
            freshness_score=80,
            final_score=85,
            status=OpportunityStatus.RECOMMENDED,
        )
        session.add(match)
        await session.commit()
    await engine.dispose()

    counts = await reclassify_legacy_rows(local_settings)

    verification_engine = make_engine(database_url)
    verification_factory = async_sessionmaker(verification_engine, expire_on_commit=False)
    async with verification_factory() as session:
        stored_opportunity = await session.scalar(select(Opportunity))
        stored_match = await session.scalar(select(UserOpportunity))
        assert stored_opportunity.content_category in {
            ContentCategory.JOB_SEEKER,
            ContentCategory.RESUME,
        }
        assert stored_opportunity.classification_version == "intent-v1"
        assert stored_opportunity.status == OpportunityStatus.FILTERED
        assert stored_match.status == OpportunityStatus.FILTERED
    assert counts["job_seeker"] + counts["resume"] == 1
    await verification_engine.dispose()
