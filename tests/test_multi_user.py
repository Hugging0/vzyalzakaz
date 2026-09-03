from copy import deepcopy
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import make_engine
from app.models import Base, OpportunityStatus, TelegramUser, UserOpportunity
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
    pipeline = OpportunityPipeline(settings)
    service = RecommendationService(settings, profile, portfolio)

    raw = RawOpportunity(
        source="test",
        source_type="telegram",
        external_id="multi-1",
        title="Python FastAPI automation project",
        description="Looking for a Python developer for a remote FastAPI automation project",
        raw_text="Looking for a Python developer for a remote FastAPI automation project",
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
        python_match.status = OpportunityStatus.APPROVED
        python_match.proposal = "Сохранённый отклик"
        await service.refresh_existing_match(session, python_user, python_match, opportunity)
        await session.commit()
        stored = (await session.scalars(select(UserOpportunity))).all()

    assert python_match is not None
    assert python_match.user_id == python_user.id
    assert other_match is None
    assert [item.user_id for item in stored] == [python_user.id]
    assert not hasattr(opportunity, "final_score")
    assert not hasattr(opportunity, "analysis")
    assert python_match.analysis["why_recommended"][0]["source_facts"]
    assert python_match.analysis["why_recommended"][0]["profile_facts"]
    assert python_match.status == OpportunityStatus.APPROVED
    assert python_match.proposal == "Сохранённый отклик"
    await engine.dispose()


@pytest.mark.asyncio
async def test_profile_change_changes_personal_score_not_global_facts(settings, profile):
    engine = make_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    pipeline = OpportunityPipeline(settings)
    service = RecommendationService(settings, profile, settings.load_portfolio())
    async with factory() as session:
        opportunity = (
            await pipeline.process(
                session,
                RawOpportunity(
                    source="test",
                    source_type="web",
                    external_id="profile-change",
                    title="Django API",
                    raw_text="Need to build a Django backend API. Budget 50000 RUB, paid project.",
                    budget_max=50_000,
                    currency="RUB",
                    published_at=datetime.now(UTC),
                    metadata={"source_content_policy": "demand_only"},
                ),
            )
        ).opportunity
        user = await service.register_user(session, {"id": 2100, "first_name": "Developer"})
        before = deepcopy(opportunity.facts)
        first_profile = service.profile_for(user)
        first_profile.candidate.skills = ["Django", "API"]
        user.profile = first_profile.model_dump()
        await session.commit()
        first = await service.ensure_match(session, user, opportunity)
        first_score = first.final_score
        await service.reset_recommendations(session, user)
        second_profile = service.profile_for(user)
        second_profile.candidate.skills = ["Backend operations"]
        user.profile = second_profile.model_dump()
        await session.commit()
        second = await service.ensure_match(session, user, opportunity)

    assert second is not None
    assert second.final_score != first_score
    assert opportunity.facts == before
    await engine.dispose()
