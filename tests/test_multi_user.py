from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import make_engine
from app.models import Base, TelegramUser, UserOpportunity
from app.schemas import RawOpportunity
from app.services.pipeline import OpportunityPipeline
from app.services.recommendations import RecommendationService


@pytest.mark.asyncio
async def test_registration_is_idempotent_and_profiles_are_isolated(settings, profile):
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    service = RecommendationService(settings, profile, settings.load_portfolio())

    async with session_factory() as session:
        first = await service.register_user(session, {"id": 1001, "first_name": "Alice", "username": "alice"})
        same = await service.register_user(
            session, {"id": 1001, "first_name": "Alice 2", "username": "alice2"}
        )
        second = await service.register_user(session, {"id": 1002, "first_name": "Bob"})
        count = await session.scalar(select(func.count()).select_from(TelegramUser))

    assert first.id == same.id
    assert second.id != first.id
    assert count == 2
    assert service.profile_for(same).candidate.name == "Alice"
    assert service.profile_for(second).candidate.name == "Bob"
    await engine.dispose()


@pytest.mark.asyncio
async def test_personal_matches_do_not_leak_between_users(settings, profile):
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    portfolio = settings.load_portfolio()
    pipeline = OpportunityPipeline(settings, profile, portfolio)
    service = RecommendationService(settings, profile, portfolio)

    raw = RawOpportunity(
        source="test",
        source_type="telegram",
        external_id="multi-1",
        title="Python FastAPI automation project",
        description="Remote freelance project: Python FastAPI Telegram bot API automation",
        raw_text="Remote freelance project: Python FastAPI Telegram bot API automation",
        published_at=datetime.now(UTC),
        remote=True,
    )
    async with session_factory() as session:
        opportunity = (await pipeline.process(session, raw)).opportunity
        python_user = await service.register_user(session, {"id": 2001, "first_name": "Python"})
        other_user = await service.register_user(session, {"id": 2002, "first_name": "Other"})
        python_profile = service.profile_for(python_user)
        python_profile.candidate.skills = ["Python", "FastAPI", "automation"]
        python_profile.ranking.digest_threshold = 50
        python_user.profile = python_profile.model_dump()
        other_profile = service.profile_for(other_user)
        other_profile.candidate.skills = ["Go"]
        other_profile.candidate.secondary_skills = []
        other_user.profile = other_profile.model_dump()
        other_user.portfolio = []
        await session.commit()

        python_match = await service.ensure_match(session, python_user, opportunity)
        other_match = await service.ensure_match(session, other_user, opportunity)
        stored = (await session.scalars(select(UserOpportunity))).all()

    assert python_match is not None
    assert python_match.user_id == python_user.id
    assert other_match is None
    assert [item.user_id for item in stored] == [python_user.id]
    await engine.dispose()
