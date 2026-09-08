from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import Candidate, CandidateProfile, SourceConfig
from app.database import make_engine
from app.models import Base, CollectorCheckpoint, ContentCategory, Opportunity, TelegramUser
from app.schemas import OpportunityFacts, RawOpportunity
from app.services.content_classifier import ContentClassification
from app.services.matching import UserMatchAnalyzer, deterministic_match
from app.services.message_tasks import split_message_tasks
from app.services.opportunity_facts import deterministic_facts
from app.services.recommendations import RecommendationService
from app.telegram.collector import TelegramCollector


def row(index, source="test", days=0):
    return Opportunity(
        source=source,
        source_type="web",
        external_id=str(index),
        title="Монтаж ролика",
        raw_text="Монтаж ролика",
        description="Монтаж ролика",
        normalized_hash=str(index).zfill(64),
        content_category=ContentCategory.PROJECT,
        published_at=datetime.now(UTC) - timedelta(days=days),
        facts={"title": "Монтаж ролика", "category": "project"},
        facts_version="facts-v3",
    )


def test_new_profile_has_no_unasked_budget():
    p = CandidateProfile(candidate=Candidate())
    assert p.economics.minimum_project_rub == 0
    assert p.economics.target_hourly_rub == 0


@pytest.mark.parametrize("kind", ["Full-Time", "Full Time", "full_time"])
def test_fulltime_aliases_cannot_escape(settings, profile, kind):
    user = TelegramUser(telegram_user_id=1, profile=profile.model_dump(), portfolio=[])
    decision = UserMatchAnalyzer(settings).cheap_eligibility(
        user, row(1), OpportunityFacts(work_type=kind), profile
    )
    assert "full_time" in decision.reasons


def test_hourly_is_compared_to_hourly_not_project(settings, profile):
    profile.economics.minimum_project_rub = 10000
    profile.economics.target_hourly_rub = 2000
    user = TelegramUser(telegram_user_id=1, profile=profile.model_dump(), portfolio=[])
    facts = OpportunityFacts(
        work_type="hourly",
        budget_unit="hour",
        currency="RUB",
        budget_max=3000,
        normalized_budget_max_rub=3000,
        fx_status="same_currency",
    )
    assert UserMatchAnalyzer(settings).cheap_eligibility(user, row(1), facts, profile).passed


def test_missing_budget_not_penalized(profile):
    missing = OpportunityFacts(title="Монтаж ролика")
    known = missing.model_copy(
        update={"budget_max": 20000, "normalized_budget_max_rub": 20000, "fx_status": "same_currency"}
    )
    a = deterministic_match(row(1), missing, profile, [], retrieval_score=70)
    b = deterministic_match(row(1), known, profile, [], retrieval_score=70)
    assert a.feature_vector["economics_fit"] == b.feature_vector["economics_fit"]
    assert a.dimensions["money"].label != "Отлично"


def test_reactions_is_not_react_and_alternatives_not_mandatory(profile):
    raw = RawOpportunity(
        source="test",
        source_type="web",
        external_id="1",
        title="Video edit",
        raw_text="Edit reactions and footage. Use Premiere Pro or DaVinci Resolve, your choice.",
    )
    classification = ContentClassification(
        category=ContentCategory.PROJECT, confidence=0.9, method="deterministic", reasons=["test"]
    )
    facts = deterministic_facts(raw, classification)
    assert "React" not in facts.skills
    assert facts.alternative_skill_groups == [["Adobe Premiere Pro", "DaVinci Resolve"]]
    profile.candidate.skills = ["Adobe Premiere Pro"]
    facts.skills = ["Adobe Premiere Pro", "DaVinci Resolve"]
    result = deterministic_match(row(1), facts, profile, [])
    assert result.missing_must_haves == []
    assert result.feature_vector["skill_overlap"] == 100


def test_digest_tasks_do_not_share_budget_or_contact():
    raw = RawOpportunity(
        source="telegram",
        source_type="telegram",
        external_id="-1001:22",
        raw_text="#дизайнер\nНужно разработать логотип по готовому ТЗ. Контакт @designer_one\n\n"
        "#монтажер\nНужно смонтировать ролик за 4000 рублей. Контакт @editor_two",
    )
    parts = split_message_tasks(raw)
    assert len(parts) == 2
    assert "@editor_two" not in parts[0].raw_text and "4000" not in parts[0].raw_text
    assert "@designer_one" not in parts[1].raw_text
    assert len({part.external_id for part in parts}) == 2
    one = raw.model_copy(
        update={
            "raw_text": "#требования\nНужен дизайнер с опытом создания логотипов.\n"
            "#условия\nРазовая задача с оплатой по результату, контакт @designer_one"
        }
    )
    assert len(split_message_tasks(one)) == 1


@pytest.mark.asyncio
async def test_backfill_includes_quiet_source_beyond_latest_200(settings, profile):
    engine = make_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    retriever = SimpleNamespace(retrieve=AsyncMock(return_value=[]))
    service = RecommendationService(settings, profile, [], retriever=retriever)
    async with factory() as session:
        user = TelegramUser(telegram_user_id=1, profile=profile.model_dump(), portfolio=[])
        quiet = row(1000, "quiet", 2)
        expired = row(1001, "expired", 30)
        session.add_all([user, quiet, expired, *[row(i, "noisy") for i in range(205)]])
        await session.commit()
        await service.backfill_user(session, user)
        candidates = retriever.retrieve.await_args.args[4]
        assert len(candidates) == 206
        assert quiet.id in {o.id for o, f in candidates}
        assert expired.id not in {o.id for o, f in candidates}
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("interruption", ["failure", "time_budget"])
async def test_telegram_checkpoint_retains_failed_message_across_restart(settings, monkeypatch, interruption):
    engine = make_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    source = SourceConfig(name="tg", type="telegram", collector="telethon", channel="@test")
    async with factory() as session:
        session.add(CollectorCheckpoint(source="tg", last_message_id=10))
        await session.commit()
    kwargs_seen = []

    class Client:
        def iter_messages(self, entity, **kwargs):
            kwargs_seen.append(kwargs)

            async def messages():
                for i in [11, 12, 13]:
                    if i > kwargs["min_id"]:
                        yield SimpleNamespace(id=i, message="text")

            return messages()

    collector = object.__new__(TelegramCollector)
    collector.settings = settings
    collector.session_factory = factory
    collector.client = Client()
    collector._process_message = AsyncMock(side_effect=[1, RuntimeError("temporary")])
    if interruption == "time_budget":
        ticks = iter([0, 31, 40, 40, 40])
        monkeypatch.setattr("app.telegram.collector.monotonic", lambda: next(ticks))
        collector._process_message = AsyncMock(return_value=1)
    await collector._poll_source(None, source)
    async with factory() as session:
        assert (await session.get(CollectorCheckpoint, "tg")).last_message_id == 11
    collector._process_message = AsyncMock(return_value=1)
    await collector._poll_source(None, source)
    assert kwargs_seen[-1]["min_id"] == 11
    assert [call.args[0].id for call in collector._process_message.await_args_list] == [12, 13]
    async with factory() as session:
        assert (await session.get(CollectorCheckpoint, "tg")).last_message_id == 13
    await engine.dispose()


def test_no_skills_does_not_receive_unearned_skill_score(profile):
    result = deterministic_match(row(1), OpportunityFacts(title="Продать приложение"), profile, [])
    assert result.feature_vector["skill_overlap"] == 0


@pytest.mark.parametrize("text", ["Примерный объем 12-16 видео в месяц", "Ведение и развитие двух сообществ"])
def test_recurring_copy_overrides_unknown_legacy_fact(settings, profile, text):
    profile.preferred.part_time = False
    opportunity = row(1)
    opportunity.raw_text = text
    user = TelegramUser(telegram_user_id=1, profile=profile.model_dump(), portfolio=[])
    result = UserMatchAnalyzer(settings).cheap_eligibility(user, opportunity, OpportunityFacts(), profile)
    assert "recurring_work" in result.reasons
