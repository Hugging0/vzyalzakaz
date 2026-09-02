from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import make_engine
from app.extension_api import CommandResult
from app.models import (
    ApplicationCommandStatus,
    Base,
    Opportunity,
    OpportunityStatus,
    TelegramUser,
    UserOpportunity,
)
from app.services.application_commands import (
    claim_next_command,
    create_application_command,
    source_for_application,
    update_command_status,
)
from app.services.extension_sessions import (
    create_extension_link_ticket,
    exchange_extension_link_ticket,
    extension_from_token,
    revoke_extension_installation,
)


async def _records(session, profile, suffix: str = "1"):
    user = TelegramUser(
        telegram_user_id=9200 + int(suffix),
        first_name="Extension user",
        profile=profile.model_dump(),
        portfolio=[
            {
                "slug": "fastapi",
                "title": "FastAPI",
                "description": "Production API",
                "skills": ["Python", "FastAPI"],
                "url": "https://portfolio.example/fastapi",
            }
        ],
    )
    opportunity = Opportunity(
        source="freelancer_com",
        source_type="api",
        source_url="https://www.freelancer.com/projects/python/build-fastapi-service",
        external_id=f"extension-{suffix}",
        title="Build a FastAPI service",
        description="Implement a production API",
        raw_text="Implement a production FastAPI service",
        normalized_hash=f"extension-{suffix}",
        published_at=datetime.now(UTC),
    )
    session.add_all([user, opportunity])
    await session.flush()
    match = UserOpportunity(
        user_id=user.id,
        opportunity_id=opportunity.id,
        prefilter_score=90,
        fit_score=92,
        money_score=80,
        win_score=75,
        freshness_score=100,
        final_score=88,
        proposal="Здравствуйте! Готов реализовать API.",
        portfolio_item="fastapi",
        status=OpportunityStatus.APPROVED,
    )
    session.add(match)
    await session.commit()
    return user, opportunity, match


@pytest.mark.asyncio
async def test_extension_link_is_one_time_and_revocable(settings, profile):
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        user, _, _ = await _records(session, profile)
        code, _ = await create_extension_link_ticket(session, user, settings)
        installation, token = await exchange_extension_link_ticket(
            session, code, "installation_123456", "chrome", "0.1.0", settings
        )
        assert (await extension_from_token(session, token)).id == installation.id
        with pytest.raises(HTTPException) as reused:
            await exchange_extension_link_ticket(
                session, code, "another_installation", "edge", "0.1.0", settings
            )
        assert reused.value.status_code == 401

        await revoke_extension_installation(session, user, installation.id)
        assert await extension_from_token(session, token) is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_command_is_idempotent_owned_and_replay_safe(settings, profile):
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        user, opportunity, match = await _records(session, profile)
        code, _ = await create_extension_link_ticket(session, user, settings)
        installation, _ = await exchange_extension_link_ticket(
            session, code, "installation_123456", "chrome", "0.1.0", settings
        )
        first = await create_application_command(
            session, settings, user, match, opportunity, "same-request"
        )
        second = await create_application_command(
            session, settings, user, match, opportunity, "same-request"
        )
        active_with_new_key = await create_application_command(
            session, settings, user, match, opportunity, "another-request"
        )
        assert first.id == second.id
        assert active_with_new_key.id == first.id
        assert first.payload["knownAnswers"]["cover_letter"] == match.proposal
        assert first.payload["knownAnswers"]["portfolio_url"].startswith("https://")
        assert first.payload["metadata"]["canSubmit"] is False

        claimed = await claim_next_command(session, installation)
        assert claimed.id == first.id
        assert claimed.status == ApplicationCommandStatus.DELIVERED
        replay = await claim_next_command(session, installation)
        assert replay.id == first.id

        for status in (
            ApplicationCommandStatus.OPENING_PAGE,
            ApplicationCommandStatus.PAGE_READY,
            ApplicationCommandStatus.FORM_FOUND,
            ApplicationCommandStatus.FILLING,
            ApplicationCommandStatus.READY_FOR_REVIEW,
            ApplicationCommandStatus.SUBMITTED,
        ):
            claimed = await update_command_status(
                session,
                installation,
                claimed.id,
                status,
                result={"filledCount": 3, "attentionCount": 0},
            )
        assert claimed.status == ApplicationCommandStatus.SUBMITTED
        assert claimed.result["filledCount"] == 3
        assert match.status == OpportunityStatus.CONTACTED
        with pytest.raises(HTTPException) as terminal:
            await update_command_status(
                session,
                installation,
                claimed.id,
                ApplicationCommandStatus.CANCELLED,
            )
        assert terminal.value.status_code == 409

    await engine.dispose()


def test_application_url_must_match_configured_https_host(settings):
    source = source_for_application(
        settings,
        "freelancer_com",
        "https://www.freelancer.com/projects/python/example",
    )
    assert source.adapter_id == "freelancer_com"
    for unsafe_url in (
        "http://www.freelancer.com/projects/1",
        "https://freelancer.com.evil.example/projects/1",
        "https://user:password@freelancer.com/projects/1",
        "javascript:alert(1)",
    ):
        with pytest.raises(HTTPException):
            source_for_application(settings, "freelancer_com", unsafe_url)


def test_extension_sources_declare_explicit_adapter_contract(settings):
    sources = {source.name: source for source in settings.load_sources()}
    for source_name in ("freelancer_com", "freelance_ru", "fl_ru", "kwork_projects"):
        source = sources[source_name]
        assert source.submission_type == "browser_extension"
        assert source.adapter_id == source_name
        assert source.application_hosts
        assert "browser_autofill" in source.capabilities
        assert "requires_confirmation" in source.capabilities


def test_command_result_serializes_shared_camel_case_contract():
    payload = CommandResult.model_validate(
        {
            "adapterVersion": "1.0.0",
            "filledCount": 2,
            "attentionCount": 1,
            "filledFields": ["Текст", "Ставка"],
            "attentionFields": ["Срок"],
        }
    ).model_dump(by_alias=True)
    assert payload == {
        "adapterVersion": "1.0.0",
        "filledCount": 2,
        "attentionCount": 1,
        "filledFields": ["Текст", "Ставка"],
        "attentionFields": ["Срок"],
    }
