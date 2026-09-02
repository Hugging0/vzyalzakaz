from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AppSettings, CandidateProfile, PortfolioProject, SourceConfig
from app.models import (
    ApplicationCommand,
    ApplicationCommandStatus,
    ExtensionInstallation,
    Opportunity,
    OpportunityStatus,
    TelegramUser,
    UserOpportunity,
)
from app.services.application_workflow import record_event, transition_application

TERMINAL_COMMAND_STATUSES = {
    ApplicationCommandStatus.SUBMITTED,
    ApplicationCommandStatus.FAILED,
    ApplicationCommandStatus.CANCELLED,
    ApplicationCommandStatus.EXPIRED,
}

COMMAND_TRANSITIONS: dict[ApplicationCommandStatus, set[ApplicationCommandStatus]] = {
    ApplicationCommandStatus.QUEUED: {
        ApplicationCommandStatus.DELIVERED,
        ApplicationCommandStatus.CANCELLED,
        ApplicationCommandStatus.EXPIRED,
    },
    ApplicationCommandStatus.DELIVERED: {
        ApplicationCommandStatus.OPENING_PAGE,
        ApplicationCommandStatus.WAITING_FOR_AUTH,
        ApplicationCommandStatus.PAGE_READY,
        ApplicationCommandStatus.FAILED,
        ApplicationCommandStatus.CANCELLED,
        ApplicationCommandStatus.EXPIRED,
    },
    ApplicationCommandStatus.OPENING_PAGE: {
        ApplicationCommandStatus.WAITING_FOR_AUTH,
        ApplicationCommandStatus.PAGE_READY,
        ApplicationCommandStatus.FAILED,
        ApplicationCommandStatus.CANCELLED,
        ApplicationCommandStatus.EXPIRED,
    },
    ApplicationCommandStatus.WAITING_FOR_AUTH: {
        ApplicationCommandStatus.OPENING_PAGE,
        ApplicationCommandStatus.PAGE_READY,
        ApplicationCommandStatus.CANCELLED,
        ApplicationCommandStatus.EXPIRED,
    },
    ApplicationCommandStatus.PAGE_READY: {
        ApplicationCommandStatus.FORM_FOUND,
        ApplicationCommandStatus.WAITING_FOR_AUTH,
        ApplicationCommandStatus.FAILED,
        ApplicationCommandStatus.CANCELLED,
        ApplicationCommandStatus.EXPIRED,
    },
    ApplicationCommandStatus.FORM_FOUND: {
        ApplicationCommandStatus.FILLING,
        ApplicationCommandStatus.FAILED,
        ApplicationCommandStatus.CANCELLED,
        ApplicationCommandStatus.EXPIRED,
    },
    ApplicationCommandStatus.FILLING: {
        ApplicationCommandStatus.PARTIALLY_FILLED,
        ApplicationCommandStatus.READY_FOR_REVIEW,
        ApplicationCommandStatus.FAILED,
        ApplicationCommandStatus.CANCELLED,
        ApplicationCommandStatus.EXPIRED,
    },
    ApplicationCommandStatus.PARTIALLY_FILLED: {
        ApplicationCommandStatus.FILLING,
        ApplicationCommandStatus.READY_FOR_REVIEW,
        ApplicationCommandStatus.CANCELLED,
        ApplicationCommandStatus.EXPIRED,
    },
    ApplicationCommandStatus.READY_FOR_REVIEW: {
        ApplicationCommandStatus.SUBMITTED,
        ApplicationCommandStatus.CANCELLED,
        ApplicationCommandStatus.EXPIRED,
    },
}


def source_for_application(
    settings: AppSettings,
    source_id: str,
    job_url: str | None,
) -> SourceConfig:
    source = next((item for item in settings.load_sources() if item.name == source_id), None)
    if source is None or source.submission_type != "browser_extension":
        raise HTTPException(409, "Для этой площадки расширение пока недоступно")
    if not ({"autofill", "browser_autofill"} & set(source.capabilities)):
        raise HTTPException(409, "Площадка не разрешает автозаполнение")
    if not job_url:
        raise HTTPException(409, "У заказа отсутствует ссылка на площадку")
    parsed = urlparse(job_url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not hostname or parsed.username or parsed.password:
        raise HTTPException(400, "Некорректная ссылка на площадку")
    allowed = {host.lower().rstrip(".") for host in source.application_hosts}
    if not allowed or not any(hostname == host or hostname.endswith(f".{host}") for host in allowed):
        raise HTTPException(400, "Домен заказа не соответствует площадке")
    return source


def build_application_payload(
    user: TelegramUser,
    match: UserOpportunity,
    opportunity: Opportunity,
    source: SourceConfig,
) -> dict:
    profile = CandidateProfile.model_validate(user.profile)
    portfolio = [PortfolioProject.model_validate(item) for item in (user.portfolio or [])]
    selected = next((item for item in portfolio if item.slug == match.portfolio_item), None)
    ui = (user.profile or {}).get("ui", {})
    saved_answers = ui.get("application_answers", {})
    known_answers = {
        "cover_letter": match.proposal,
        "rate": profile.economics.target_hourly_rub,
    }
    for key in ("github", "website", "experience"):
        value = saved_answers.get(key)
        if isinstance(value, str) and value.strip():
            known_answers[key] = value.strip()
    if selected and selected.url:
        known_answers["portfolio_url"] = selected.url
    return {
        "applicationId": match.id,
        "sourceId": source.adapter_id or source.name,
        "jobUrl": opportunity.source_url,
        "coverLetter": match.proposal,
        "selectedPortfolioCase": selected.model_dump(mode="json") if selected else None,
        "knownAnswers": known_answers,
        "attachments": [],
        "metadata": {
            "jobTitle": opportunity.title,
            "sourceName": source.display_name or source.name,
            "requiresConfirmation": "requires_confirmation" in source.capabilities,
            "canSubmit": "browser_submit" in source.capabilities,
        },
    }


async def create_application_command(
    session: AsyncSession,
    settings: AppSettings,
    user: TelegramUser,
    match: UserOpportunity,
    opportunity: Opportunity,
    idempotency_key: str,
) -> ApplicationCommand:
    existing = await session.scalar(
        select(ApplicationCommand).where(
            ApplicationCommand.user_id == user.id,
            ApplicationCommand.idempotency_key == idempotency_key,
        )
    )
    if existing:
        return existing
    active = await session.scalar(
        select(ApplicationCommand).where(
            ApplicationCommand.user_id == user.id,
            ApplicationCommand.user_opportunity_id == match.id,
            ApplicationCommand.status.not_in(TERMINAL_COMMAND_STATUSES),
        )
    )
    if active:
        return active
    source = source_for_application(settings, opportunity.source, opportunity.source_url)
    now = datetime.now(UTC)
    command = ApplicationCommand(
        user_id=user.id,
        user_opportunity_id=match.id,
        idempotency_key=idempotency_key,
        source_id=source.adapter_id or source.name,
        job_url=opportunity.source_url or "",
        payload=build_application_payload(user, match, opportunity, source),
        status=ApplicationCommandStatus.QUEUED,
        expires_at=now + timedelta(seconds=settings.extension_command_ttl_seconds),
    )
    session.add(command)
    await record_event(session, match, "extension_command_queued", actor="web")
    await session.commit()
    await session.refresh(command)
    return command


async def expire_commands(session: AsyncSession) -> None:
    now = datetime.now(UTC)
    await session.execute(
        update(ApplicationCommand)
        .where(
            ApplicationCommand.expires_at <= now,
            ApplicationCommand.status.not_in(TERMINAL_COMMAND_STATUSES),
        )
        .values(status=ApplicationCommandStatus.EXPIRED, completed_at=now, updated_at=now)
        .execution_options(synchronize_session=False)
    )


async def claim_next_command(
    session: AsyncSession,
    installation: ExtensionInstallation,
) -> ApplicationCommand | None:
    await expire_commands(session)
    active = await session.scalar(
        select(ApplicationCommand)
        .where(
            ApplicationCommand.user_id == installation.user_id,
            ApplicationCommand.claimed_installation_id == installation.id,
            ApplicationCommand.status.not_in(TERMINAL_COMMAND_STATUSES),
        )
        .order_by(ApplicationCommand.created_at.asc())
        .limit(1)
    )
    if active:
        await session.commit()
        return active
    command = await session.scalar(
        select(ApplicationCommand)
        .where(
            ApplicationCommand.user_id == installation.user_id,
            ApplicationCommand.status == ApplicationCommandStatus.QUEUED,
        )
        .order_by(ApplicationCommand.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if command is None:
        await session.commit()
        return None
    now = datetime.now(UTC)
    command.claimed_installation_id = installation.id
    command.status = ApplicationCommandStatus.DELIVERED
    command.delivered_at = now
    command.updated_at = now
    match = await session.get(UserOpportunity, command.user_opportunity_id)
    if match:
        await record_event(session, match, "extension_command_delivered", actor="extension")
    await session.commit()
    await session.refresh(command)
    return command


async def update_command_status(
    session: AsyncSession,
    installation: ExtensionInstallation,
    command_id: UUID,
    new_status: ApplicationCommandStatus,
    *,
    result: dict | None = None,
    error_code: str | None = None,
    error_detail: str | None = None,
) -> ApplicationCommand:
    command = await session.get(ApplicationCommand, command_id)
    if command is None or command.user_id != installation.user_id:
        raise HTTPException(404, "Команда не найдена")
    if command.claimed_installation_id != installation.id:
        raise HTTPException(409, "Команда выполняется другим экземпляром расширения")
    if command.status == new_status:
        return command
    if command.status in TERMINAL_COMMAND_STATUSES:
        raise HTTPException(409, "Команда уже завершена")
    if command.expires_at.replace(tzinfo=command.expires_at.tzinfo or UTC) <= datetime.now(UTC):
        command.status = ApplicationCommandStatus.EXPIRED
        command.completed_at = datetime.now(UTC)
        await session.commit()
        raise HTTPException(410, "Срок команды истёк")
    allowed = COMMAND_TRANSITIONS.get(command.status, set())
    if new_status not in allowed:
        raise HTTPException(409, f"Недопустимый переход {command.status.value} → {new_status.value}")

    now = datetime.now(UTC)
    command.status = new_status
    command.updated_at = now
    if result is not None:
        command.result = result
    command.error_code = error_code
    command.error_detail = error_detail[:255] if error_detail else None
    if new_status in TERMINAL_COMMAND_STATUSES:
        command.completed_at = now
    match = await session.get(UserOpportunity, command.user_opportunity_id)
    if match:
        detail = command.error_detail if new_status == ApplicationCommandStatus.FAILED else None
        await record_event(
            session,
            match,
            f"extension_{new_status.value}",
            actor="extension",
            detail=detail,
        )
        if new_status == ApplicationCommandStatus.SUBMITTED:
            if match.status == OpportunityStatus.RECOMMENDED:
                await transition_application(
                    session,
                    match,
                    OpportunityStatus.APPROVED,
                    actor="extension",
                    detail="Отклик подтверждён в браузере",
                )
            if match.status == OpportunityStatus.APPROVED:
                await transition_application(
                    session,
                    match,
                    OpportunityStatus.CONTACTED,
                    actor="extension",
                    detail="Площадка подтвердила отправку",
                )
    await session.commit()
    await session.refresh(command)
    return command


def command_payload(command: ApplicationCommand) -> dict:
    result = {
        "filledCount": 0,
        "attentionCount": 0,
        "filledFields": [],
        "attentionFields": [],
        **(command.result or {}),
    }
    return {
        "id": str(command.id),
        **command.payload,
        "status": command.status.value,
        "expiresAt": command.expires_at.isoformat(),
        "result": result,
        "error": (
            {"code": command.error_code, "message": command.error_detail}
            if command.error_code
            else None
        ),
    }
