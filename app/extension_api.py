from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AppSettings, get_settings
from app.database import get_session
from app.mini_app_auth import current_mini_app_user
from app.models import (
    ApplicationCommand,
    ApplicationCommandStatus,
    ExtensionDiagnostic,
    ExtensionInstallation,
    Opportunity,
    OpportunityStatus,
    TelegramUser,
    UserOpportunity,
)
from app.services.application_commands import (
    TERMINAL_COMMAND_STATUSES,
    claim_next_command,
    command_payload,
    create_application_command,
    update_command_status,
)
from app.services.extension_sessions import (
    create_extension_link_ticket,
    exchange_extension_link_ticket,
    extension_from_token,
    revoke_extension_installation,
)

router = APIRouter(prefix="/api")
extension_security = HTTPBearer(auto_error=False)
CurrentUser = Annotated[TelegramUser, Depends(current_mini_app_user)]
ERROR_CODES = Literal[
    "UNSUPPORTED_SOURCE",
    "UNSUPPORTED_PAGE",
    "AUTH_REQUIRED",
    "FORM_NOT_FOUND",
    "FORM_CHANGED",
    "FIELD_NOT_FOUND",
    "FIELD_VALIDATION_FAILED",
    "PAGE_LOAD_FAILED",
    "COMMAND_EXPIRED",
    "COMMAND_ALREADY_PROCESSED",
    "EXTENSION_OFFLINE",
    "BACKEND_UNAVAILABLE",
]
SAFE_TELEMETRY_KEYS = {
    "adapterId",
    "adapterVersion",
    "sourceId",
    "pageType",
    "fieldType",
    "fieldName",
    "filledCount",
    "attentionCount",
    "durationMs",
    "errorCode",
    "extensionVersion",
}


class LinkExchange(BaseModel):
    code: str = Field(min_length=20, max_length=80)
    installation_id: str = Field(
        validation_alias="installationId",
        min_length=16,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_-]+$",
    )
    browser: Literal["chrome", "edge", "brave", "yandex", "chromium", "firefox"] = "chromium"
    version: str = Field(min_length=1, max_length=30, pattern=r"^[0-9A-Za-z.+-]+$")


class Heartbeat(BaseModel):
    version: str = Field(min_length=1, max_length=30, pattern=r"^[0-9A-Za-z.+-]+$")
    active_source_id: str | None = Field(
        default=None, validation_alias="activeSourceId", max_length=100
    )
    marketplace_auth_state: Literal[
        "AUTHENTICATED", "AUTH_REQUIRED", "UNKNOWN", "UNSUPPORTED"
    ] | None = Field(default=None, validation_alias="marketplaceAuthState")
    last_error_code: ERROR_CODES | None = Field(
        default=None, validation_alias="lastErrorCode"
    )


class CommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter_version: str | None = Field(
        default=None,
        validation_alias="adapterVersion",
        serialization_alias="adapterVersion",
        max_length=30,
    )
    filled_count: int = Field(
        default=0,
        validation_alias="filledCount",
        serialization_alias="filledCount",
        ge=0,
        le=100,
    )
    attention_count: int = Field(
        default=0,
        validation_alias="attentionCount",
        serialization_alias="attentionCount",
        ge=0,
        le=100,
    )
    filled_fields: list[str] = Field(
        default_factory=list,
        validation_alias="filledFields",
        serialization_alias="filledFields",
        max_length=100,
    )
    attention_fields: list[str] = Field(
        default_factory=list,
        validation_alias="attentionFields",
        serialization_alias="attentionFields",
        max_length=100,
    )


class CommandStatusUpdate(BaseModel):
    status: ApplicationCommandStatus
    result: CommandResult | None = None
    error_code: ERROR_CODES | None = Field(default=None, validation_alias="errorCode")
    error_detail: str | None = Field(
        default=None, validation_alias="errorDetail", max_length=255
    )


class DiagnosticEvent(BaseModel):
    event: Literal[
        "extension_connected",
        "command_received",
        "adapter_selected",
        "auth_required",
        "form_detected",
        "field_fill_success",
        "field_fill_failed",
        "application_ready",
        "application_submitted",
        "application_failed",
    ]
    level: Literal["info", "warning", "error"] = "info"
    command_id: UUID | None = Field(default=None, validation_alias="commandId")
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class DiagnosticBatch(BaseModel):
    events: list[DiagnosticEvent] = Field(min_length=1, max_length=50)


async def current_extension(
    credentials: HTTPAuthorizationCredentials | None = Depends(extension_security),
    session: AsyncSession = Depends(get_session),
) -> ExtensionInstallation:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, "Расширение не подключено")
    installation = await extension_from_token(session, credentials.credentials)
    if installation is None:
        raise HTTPException(401, "Сессия расширения истекла или отозвана")
    return installation


CurrentExtension = Annotated[ExtensionInstallation, Depends(current_extension)]


def _installation_payload(
    installation: ExtensionInstallation,
    settings: AppSettings,
) -> dict:
    now = datetime.now(UTC)
    last_seen = installation.last_seen_at.replace(
        tzinfo=installation.last_seen_at.tzinfo or UTC
    )
    online = last_seen >= now - timedelta(seconds=settings.extension_offline_after_seconds)
    return {
        "id": str(installation.id),
        "installationId": installation.installation_id,
        "browser": installation.browser,
        "version": installation.version,
        "state": "CONNECTED" if online else "OFFLINE",
        "activeSourceId": installation.active_source_id,
        "marketplaceAuthState": installation.marketplace_auth_state,
        "lastErrorCode": installation.last_error_code,
        "lastSeenAt": installation.last_seen_at.isoformat(),
        "expiresAt": installation.expires_at.isoformat(),
    }


@router.post("/app/extension/link-tickets")
async def create_link_ticket(
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
    settings: AppSettings = Depends(get_settings),
) -> dict:
    code, ticket = await create_extension_link_ticket(session, user, settings)
    return {"code": code, "expiresAt": ticket.expires_at.isoformat()}


@router.get("/app/extension/status")
async def extension_status(
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
    settings: AppSettings = Depends(get_settings),
) -> dict:
    installations = (
        await session.scalars(
            select(ExtensionInstallation)
            .where(
                ExtensionInstallation.user_id == user.id,
                ExtensionInstallation.revoked_at.is_(None),
                ExtensionInstallation.expires_at > datetime.now(UTC),
            )
            .order_by(ExtensionInstallation.last_seen_at.desc())
        )
    ).all()
    payloads = [_installation_payload(item, settings) for item in installations]
    if not payloads:
        state = "NOT_DETECTED"
    elif any(item["state"] == "CONNECTED" for item in payloads):
        state = "CONNECTED"
    else:
        state = "OFFLINE"
    return {"state": state, "installations": payloads}


@router.delete("/app/extension/installations/{installation_id}")
async def disconnect_extension(
    installation_id: UUID,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await revoke_extension_installation(session, user, installation_id)
    return {"disconnected": True}


@router.post("/app/leads/{match_id}/application-command")
async def queue_application_command(
    match_id: int,
    request: Request,
    user: CurrentUser,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
    settings: AppSettings = Depends(get_settings),
) -> dict:
    if not idempotency_key or not 8 <= len(idempotency_key) <= 100:
        raise HTTPException(400, "Нужен корректный Idempotency-Key")
    row = await session.execute(
        select(UserOpportunity, Opportunity)
        .join(Opportunity, Opportunity.id == UserOpportunity.opportunity_id)
        .where(UserOpportunity.id == match_id, UserOpportunity.user_id == user.id)
    )
    owned = row.first()
    if owned is None:
        raise HTTPException(404, "Заказ не найден")
    match, opportunity = owned
    if match.status not in {OpportunityStatus.RECOMMENDED, OpportunityStatus.APPROVED}:
        raise HTTPException(409, "Отклик уже отправлен или заказ закрыт")
    if not match.proposal:
        await request.app.state.runtime.recommendations.generate_proposal(
            session, user, match, opportunity
        )
    command = await create_application_command(
        session,
        settings,
        user,
        match,
        opportunity,
        idempotency_key,
    )
    return command_payload(command)


@router.get("/app/leads/{match_id}/application-command")
async def latest_application_command(
    match_id: int,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict | None:
    match = await session.scalar(
        select(UserOpportunity).where(
            UserOpportunity.id == match_id,
            UserOpportunity.user_id == user.id,
        )
    )
    if match is None:
        raise HTTPException(404, "Заказ не найден")
    command = await session.scalar(
        select(ApplicationCommand)
        .where(
            ApplicationCommand.user_id == user.id,
            ApplicationCommand.user_opportunity_id == match.id,
        )
        .order_by(ApplicationCommand.created_at.desc())
        .limit(1)
    )
    return command_payload(command) if command else None


@router.post("/extension/auth/exchange")
async def exchange_link_ticket(
    payload: LinkExchange,
    session: AsyncSession = Depends(get_session),
    settings: AppSettings = Depends(get_settings),
) -> dict:
    installation, token = await exchange_extension_link_ticket(
        session,
        payload.code,
        payload.installation_id,
        payload.browser,
        payload.version,
        settings,
    )
    return {
        "token": token,
        "installation": _installation_payload(installation, settings),
    }


@router.post("/extension/heartbeat")
async def extension_heartbeat(
    payload: Heartbeat,
    installation: CurrentExtension,
    session: AsyncSession = Depends(get_session),
) -> dict:
    installation.version = payload.version
    installation.active_source_id = payload.active_source_id
    installation.marketplace_auth_state = payload.marketplace_auth_state
    installation.last_error_code = payload.last_error_code
    installation.last_seen_at = datetime.now(UTC)
    pending = await session.scalar(
        select(func.count())
        .select_from(ApplicationCommand)
        .where(
            ApplicationCommand.user_id == installation.user_id,
            ApplicationCommand.status.not_in(TERMINAL_COMMAND_STATUSES),
        )
    )
    await session.commit()
    return {"ok": True, "pendingCommands": pending or 0, "serverTime": datetime.now(UTC).isoformat()}


@router.delete("/extension/session")
async def disconnect_current_extension(
    installation: CurrentExtension,
    session: AsyncSession = Depends(get_session),
) -> dict:
    installation.revoked_at = datetime.now(UTC)
    await session.commit()
    return {"disconnected": True}


@router.get("/extension/commands/next")
async def next_extension_command(
    response: Response,
    installation: CurrentExtension,
    session: AsyncSession = Depends(get_session),
) -> dict | None:
    command = await claim_next_command(session, installation)
    if command is None:
        response.status_code = 204
        return None
    return command_payload(command)


@router.patch("/extension/commands/{command_id}")
async def patch_extension_command(
    command_id: UUID,
    payload: CommandStatusUpdate,
    installation: CurrentExtension,
    session: AsyncSession = Depends(get_session),
) -> dict:
    if payload.status == ApplicationCommandStatus.FAILED and not payload.error_code:
        raise HTTPException(422, "Для ошибки нужен тип")
    result = payload.result.model_dump(by_alias=True) if payload.result else None
    command = await update_command_status(
        session,
        installation,
        command_id,
        payload.status,
        result=result,
        error_code=payload.error_code,
        error_detail=payload.error_detail,
    )
    return command_payload(command)


@router.post("/extension/diagnostics", status_code=202)
async def record_extension_diagnostics(
    payload: DiagnosticBatch,
    installation: CurrentExtension,
    session: AsyncSession = Depends(get_session),
) -> dict:
    accepted = 0
    for item in payload.events:
        if item.command_id:
            command = await session.get(ApplicationCommand, item.command_id)
            if command is None or command.user_id != installation.user_id:
                continue
        safe_metadata = {
            key: value
            for key, value in item.metadata.items()
            if key in SAFE_TELEMETRY_KEYS
        }
        session.add(
            ExtensionDiagnostic(
                user_id=installation.user_id,
                installation_id=installation.id,
                command_id=item.command_id,
                event=item.event,
                level=item.level,
                metadata_json=safe_metadata,
            )
        )
        accepted += 1
    await session.commit()
    return {"accepted": accepted}


@router.get("/extension/sources")
async def extension_sources(
    installation: CurrentExtension,
    settings: AppSettings = Depends(get_settings),
) -> list[dict]:
    del installation
    return [
        {
            "id": source.adapter_id or source.name,
            "sourceId": source.name,
            "displayName": source.display_name or source.name,
            "hosts": source.application_hosts,
            "capabilities": source.capabilities,
        }
        for source in settings.load_sources()
        if source.submission_type == "browser_extension" and source.adapter_id
    ]
