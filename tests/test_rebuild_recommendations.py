from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import make_engine
from app.models import (
    Base,
    ClassificationMethod,
    ContentCategory,
    Opportunity,
    OpportunityStatus,
    TelegramUser,
    UserOpportunity,
)
from app.rebuild_recommendations import rebuild_recommendations


@pytest.mark.asyncio
async def test_rebuild_ignores_onboarding_limit(settings, profile, tmp_path):
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'rebuild.db'}"
    local_settings = settings.model_copy(
        update={"database_url": database_url, "onboarding_backfill_limit": 1}
    )
    engine = make_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    profile.candidate.skills = ["Python", "FastAPI", "API"]
    async with session_factory() as session:
        user = TelegramUser(
            telegram_user_id=100,
            is_active=True,
            profile=profile.model_dump(),
            portfolio=[],
        )
        session.add(user)
        for index in range(3):
            text = f"Looking for a Python FastAPI developer for paid API project {index}"
            session.add(
                Opportunity(
                    source="test",
                    source_type="web",
                    external_id=str(index),
                    title=f"Python API {index}",
                    description=text,
                    raw_text=text,
                    normalized_hash=str(index).zfill(64),
                    content_category=ContentCategory.PROJECT,
                    classification_confidence=0.9,
                    classification_method=ClassificationMethod.DETERMINISTIC,
                    classification_reasons=["test"],
                    classification_version="intent-v1",
                    status=OpportunityStatus.NEW,
                    published_at=datetime.now(UTC),
                )
            )
        await session.commit()
    await engine.dispose()

    counts = await rebuild_recommendations(local_settings)

    verification_engine = make_engine(database_url)
    verification_factory = async_sessionmaker(verification_engine, expire_on_commit=False)
    async with verification_factory() as session:
        match_count = await session.scalar(select(func.count()).select_from(UserOpportunity))
    assert counts["matches"] == 3
    assert match_count == 3
    await verification_engine.dispose()
