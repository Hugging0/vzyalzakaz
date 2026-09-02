from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import make_engine
from app.models import Base, Opportunity, OpportunityStatus, TelegramUser, UserOpportunity
from app.services.application_workflow import transition_application
from app.services.web_sessions import (
    create_login_ticket,
    exchange_login_ticket,
    revoke_web_session,
    user_from_web_session,
)
from app.telegram.bot import _web_login_destination


@pytest.mark.asyncio
async def test_web_login_ticket_is_one_time_and_session_can_be_revoked(settings, profile):
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        user = TelegramUser(
            telegram_user_id=9101,
            first_name="Web user",
            profile=profile.model_dump(),
            portfolio=[],
        )
        session.add(user)
        await session.commit()
        ticket = await create_login_ticket(session, user, settings)
        exchanged_user, web_token = await exchange_login_ticket(session, ticket, settings)

        assert exchanged_user.id == user.id
        assert (await user_from_web_session(session, web_token)).id == user.id
        with pytest.raises(HTTPException) as exc_info:
            await exchange_login_ticket(session, ticket, settings)
        assert exc_info.value.status_code == 401

        await revoke_web_session(session, web_token)
        assert await user_from_web_session(session, web_token) is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_application_workflow_rejects_skipped_steps(settings, profile):
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        user = TelegramUser(
            telegram_user_id=9102,
            first_name="Applicant",
            profile=profile.model_dump(),
            portfolio=[],
        )
        opportunity = Opportunity(
            source="test",
            source_type="web",
            external_id="workflow-1",
            title="FastAPI project",
            description="Build an API",
            raw_text="Build an API",
            normalized_hash="workflow-1",
            published_at=datetime.now(UTC),
        )
        session.add_all([user, opportunity])
        await session.flush()
        match = UserOpportunity(
            user_id=user.id,
            opportunity_id=opportunity.id,
            prefilter_score=90,
            fit_score=90,
            money_score=80,
            win_score=70,
            freshness_score=100,
            final_score=88,
            status=OpportunityStatus.RECOMMENDED,
        )
        session.add(match)
        await session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await transition_application(
                session,
                match,
                OpportunityStatus.CONTACTED,
                actor="web",
            )
        assert exc_info.value.status_code == 409

        await transition_application(session, match, OpportunityStatus.APPROVED, actor="web")
        match.proposal = "Здравствуйте, готов выполнить задачу."
        await session.commit()
        await transition_application(session, match, OpportunityStatus.CONTACTED, actor="web")
        assert match.status == OpportunityStatus.CONTACTED
        assert match.contacted_at is not None

    await engine.dispose()


def test_web_login_payload_only_allows_known_workspace_routes():
    assert _web_login_destination("web-login-order-42") == "/app/orders/42"
    assert _web_login_destination("web-login-application-7") == "/app/applications/7"
    assert _web_login_destination("web-login-settings") == "/app/settings"
    assert _web_login_destination("web-login-../../admin") == "/app/today"


def test_browser_extension_sources_declare_capabilities(settings):
    sources = {source.name: source for source in settings.load_sources()}
    for source_name in ("freelance_ru", "fl_ru", "kwork_projects"):
        source = sources[source_name]
        assert source.submission_type == "browser_extension"
        assert {"autofill", "requires_confirmation"}.issubset(source.capabilities)
