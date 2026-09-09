import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import make_engine
from app.models import Base, CompatibilityCache, ContentCategory, Opportunity, TelegramUser, UserOpportunity
from app.schemas import OpportunityFacts
from app.services.compatibility import CompatibilityGuard, Decision, grounded
from app.services.recommendations import RecommendationService
from app.services.retrieval import RetrievalCandidate


def candidate(index, title):
    opportunity = Opportunity(
        source="test",
        source_type="web",
        external_id=str(index),
        title=title,
        description=title,
        raw_text=title,
        normalized_hash=str(index).zfill(64),
        content_category=ContentCategory.PROJECT,
    )
    facts = OpportunityFacts(title=title, category="project")
    return RetrievalCandidate(opportunity, facts, 80, 80, 80, False)


def decision(key, title, verdict="unsuitable", profile_quote="React"):
    return {
        "id": key,
        "verdict": verdict,
        "confidence": 0.95,
        "reason": "The task requires selling, not web development.",
        "source_quote": title,
        "profile_quote": profile_quote,
    }


def test_rejection_requires_verbatim_evidence_on_both_sides():
    valid = Decision(**decision("1", "Продать приложение"))
    assert grounded(valid, "Нужно продать приложение", '{"skills": ["React"]}')
    assert not grounded(valid, "Создать приложение", '{"skills": ["React"]}')
    assert not grounded(valid, "Продать приложение", '{"skills": ["Python"]}')


@pytest.mark.asyncio
async def test_cache_invalidation_and_unrelated_task_exclusion(settings, profile):
    engine = make_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    profile.candidate.skills = ["React"]
    bad, good = candidate(901, "Продать приложение"), candidate(902, "React landing page")

    async def complete(prompt, **kwargs):
        tasks = json.loads(prompt.split("\nTASKS:\n")[1])
        return {
            "decisions": [
                decision(k, v, "unsuitable" if "Продать" in v else "suitable") for k, v in tasks.items()
            ]
        }

    client = SimpleNamespace(available=True, complete=AsyncMock(side_effect=complete))
    guard = CompatibilityGuard(settings, client)
    async with factory() as session:
        user = TelegramUser(telegram_user_id=901, profile=profile.model_dump(), portfolio=[])
        session.add_all([user, bad.opportunity, good.opportunity])
        await session.flush()
        assert await guard.filter(session, user, profile, [], [bad, good]) == [good]
        await session.commit()
        assert await session.scalar(select(func.count()).select_from(CompatibilityCache)) == 2
        assert await guard.filter(session, user, profile, [], [bad, good]) == [good]
        assert client.complete.await_count == 1
        profile.candidate.about += " I can sell software too."
        await guard.filter(session, user, profile, [], [bad, good])
        assert client.complete.await_count == 2
        bad.opportunity.raw_text += " Updated conditions."
        await guard.filter(session, user, profile, [], [bad, good])
        assert client.complete.await_count == 3
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["invented_quote", "missing_id", "provider"])
async def test_unverified_rejections_are_not_applied_or_cached(settings, profile, failure):
    engine = make_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    item = candidate(903, "React landing page")
    profile.candidate.skills = ["React"]

    async def complete(prompt, **kwargs):
        if failure == "provider":
            raise RuntimeError("provider unavailable")
        tasks = json.loads(prompt.split("\nTASKS:\n")[1])
        return {
            "decisions": []
            if failure == "missing_id"
            else [decision(k, "invented mandatory requirement") for k in tasks]
        }

    guard = CompatibilityGuard(settings, SimpleNamespace(available=True, complete=complete))
    async with factory() as session:
        user = TelegramUser(telegram_user_id=903, profile=profile.model_dump(), portfolio=[])
        session.add_all([user, item.opportunity])
        await session.flush()
        assert await guard.filter(session, user, profile, [], [item]) == [item]
        assert await session.scalar(select(func.count()).select_from(CompatibilityCache)) == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_live_match_does_not_persist_proven_incompatible_task(settings, profile):
    engine = make_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    profile.candidate.skills = ["React"]
    item = candidate(904, "Продать приложение")
    item.opportunity.facts = item.facts.model_dump()
    item.opportunity.facts_version = "facts-v3"
    retriever = SimpleNamespace(retrieve=AsyncMock(return_value=[item]))
    service = RecommendationService(settings, profile, [], retriever)
    service.compatibility.filter = AsyncMock(return_value=[])
    async with factory() as session:
        user = TelegramUser(telegram_user_id=904, profile=profile.model_dump(), portfolio=[])
        session.add_all([user, item.opportunity])
        await session.flush()
        assert await service.ensure_match(session, user, item.opportunity) is None
        assert await session.scalar(select(func.count()).select_from(UserOpportunity)) == 0
        service.compatibility.filter.assert_awaited_once()
    await engine.dispose()


@pytest.mark.asyncio
async def test_recurring_requirement_cannot_be_overruled_by_skill_match(settings):
    reply = decision("one", "Publish six posts every day", verdict="suitable", profile_quote="SMM")
    reply["required_ongoing_work"] = True
    client = SimpleNamespace(available=True, complete=AsyncMock(return_value={"decisions": [reply]}))
    guard = CompatibilityGuard(settings, client)
    results = await guard._batch(
        "Ongoing work allowed: False. Skills: SMM", {"one": "Publish six posts every day"}
    )
    assert results[0].verdict == "unsuitable"
    assert results[0].profile_quote == "Ongoing work allowed: False"


@pytest.mark.asyncio
async def test_verbose_item_does_not_discard_other_valid_assessments(settings):
    text = "React " * 100
    replies = [decision("one", text, verdict="suitable"), decision("two", "Sell software")]
    replies[0]["reason"] = "Reason " * 100
    client = SimpleNamespace(available=True, complete=AsyncMock(return_value={"decisions": replies}))
    guard = CompatibilityGuard(settings, client)
    results = await guard._batch("Skills: React", {"one": text, "two": "Sell software"})
    assert len(results) == 2
    assert results[1].verdict == "unsuitable"


@pytest.mark.asyncio
async def test_timeout_preserves_completed_batches(settings, profile):
    import asyncio

    settings.matching_compatibility_timeout_seconds = 1
    settings.matching_compatibility_batch_size = 1
    engine = make_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    profile.candidate.skills = ["React"]
    bad, slow = candidate(910, "Sell software"), candidate(911, "Slow task")

    async def complete(prompt, **kwargs):
        tasks = json.loads(prompt.split("\nTASKS:\n")[1])
        if "Slow task" in next(iter(tasks.values())):
            await asyncio.sleep(10)
        return {"decisions": [decision(k, v) for k, v in tasks.items()]}

    guard = CompatibilityGuard(settings, SimpleNamespace(available=True, complete=complete))
    async with factory() as session:
        user = TelegramUser(telegram_user_id=910, profile=profile.model_dump(), portfolio=[])
        session.add_all([user, bad.opportunity, slow.opportunity])
        await session.flush()
        kept = await guard.filter(session, user, profile, [], [bad, slow])
        assert kept == [slow]
    await engine.dispose()
