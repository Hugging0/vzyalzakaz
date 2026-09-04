from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AppSettings
from app.database import get_session
from app.integrations.hh.client import HHClient
from app.integrations.hh.errors import HHError
from app.integrations.hh.oauth import (
    access_token_for,
    connection_for_user,
    consume_oauth_state,
    create_oauth_authorization,
    finish_oauth,
    mark_reauth_required,
    resume_payload,
)
from app.mini_app_auth import current_mini_app_user
from app.models import ExternalConnectionStatus, IntegrationAuditEvent, TelegramUser

router = APIRouter()
CurrentUser = Annotated[TelegramUser, Depends(current_mini_app_user)]


class OAuthStart(BaseModel):
    agreement_accepted: bool


class ResumeSelection(BaseModel):
    resume_id: str


@router.get("/api/app/connections/hh")
async def read_hh_connection(
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict:
    settings: AppSettings = request.app.state.runtime.settings
    connection = await connection_for_user(session, user.id)
    return _connection_payload(connection, settings)


@router.post("/api/app/connections/hh/oauth/start")
async def start_hh_oauth(
    payload: OAuthStart,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not payload.agreement_accepted:
        raise HTTPException(400, "Подтвердите соглашение HH перед подключением.")
    settings: AppSettings = request.app.state.runtime.settings
    try:
        url = await create_oauth_authorization(session, user, settings)
    except RuntimeError as exc:
        raise HTTPException(503, "Подключение HH пока не настроено.") from exc
    session.add(
        IntegrationAuditEvent(
            user_id=user.id,
            provider="hh",
            event="oauth_started",
            metadata_json={"agreement_accepted": True},
        )
    )
    await session.commit()
    return {"authorizeUrl": url}


@router.get("/api/integrations/hh/oauth/callback")
async def hh_oauth_callback(
    request: Request,
    state: str = Query(min_length=20, max_length=200),
    code: str | None = Query(default=None, max_length=500),
    error: str | None = Query(default=None, max_length=100),
    session: AsyncSession = Depends(get_session),
):
    settings: AppSettings = request.app.state.runtime.settings
    destination = (
        f"{settings.public_base_url.rstrip('/')}/app/connections"
        if settings.public_base_url
        else "/app/connections"
    )
    if error or not code:
        try:
            await consume_oauth_state(session, state)
        except HHError:
            pass
        return RedirectResponse(f"{destination}?hh=cancelled", status_code=303)
    try:
        connection = await finish_oauth(session, state, code, settings)
        await _refresh_resumes(session, connection, settings)
        session.add(
            IntegrationAuditEvent(
                user_id=connection.user_id,
                provider="hh",
                event="connected",
                metadata_json={"external_user_id": connection.external_user_id},
            )
        )
        await session.commit()
    except (HHError, RuntimeError):
        return RedirectResponse(f"{destination}?hh=error", status_code=303)
    return RedirectResponse(f"{destination}?hh=connected", status_code=303)


@router.post("/api/app/connections/hh/resumes/refresh")
async def refresh_hh_resumes(
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict:
    settings: AppSettings = request.app.state.runtime.settings
    connection = await connection_for_user(session, user.id)
    if connection is None:
        raise HTTPException(409, "Сначала подключите HH.")
    try:
        await _refresh_resumes(session, connection, settings)
    except HHError as exc:
        raise HTTPException(exc.status_code, exc.user_message) from exc
    session.add(
        IntegrationAuditEvent(
            user_id=user.id,
            provider="hh",
            event="resumes_refreshed",
            metadata_json={"count": len((connection.metadata_json or {}).get("resumes", []))},
        )
    )
    await session.commit()
    return _connection_payload(connection, settings)


@router.patch("/api/app/connections/hh/resume")
async def select_hh_resume(
    payload: ResumeSelection,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict:
    settings: AppSettings = request.app.state.runtime.settings
    connection = await connection_for_user(session, user.id)
    if connection is None:
        raise HTTPException(409, "Сначала подключите HH.")
    resumes = (connection.metadata_json or {}).get("resumes", [])
    if not any(str(item.get("id")) == payload.resume_id for item in resumes):
        raise HTTPException(400, "Это резюме недоступно в подключённом аккаунте.")
    connection.selected_resume_id = payload.resume_id
    session.add(
        IntegrationAuditEvent(
            user_id=user.id,
            provider="hh",
            event="resume_selected",
            metadata_json={"resume_id": payload.resume_id},
        )
    )
    await session.commit()
    return _connection_payload(connection, settings)


@router.delete("/api/app/connections/hh")
async def disconnect_hh(
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict:
    settings: AppSettings = request.app.state.runtime.settings
    connection = await connection_for_user(session, user.id)
    if connection:
        connection.access_token_encrypted = None
        connection.refresh_token_encrypted = None
        connection.token_expires_at = None
        connection.selected_resume_id = None
        connection.metadata_json = {}
        connection.status = ExternalConnectionStatus.REAUTH_REQUIRED
        connection.last_error_code = "disconnected"
    session.add(
        IntegrationAuditEvent(
            user_id=user.id,
            provider="hh",
            event="disconnected",
            metadata_json={},
        )
    )
    await session.commit()
    return _connection_payload(connection, settings)


async def _refresh_resumes(session, connection, settings: AppSettings) -> None:
    client = HHClient(settings)
    access_token = await access_token_for(session, connection, settings, client=client)
    try:
        payload = await client.resumes(access_token)
    except HHError as exc:
        if exc.code == "auth_required":
            mark_reauth_required(connection)
            await session.commit()
        raise
    raw_items = payload.get("items") if isinstance(payload, dict) else payload
    resumes = [resume_payload(item) for item in (raw_items or []) if item.get("id")]
    connection.metadata_json = {**(connection.metadata_json or {}), "resumes": resumes}
    available = {item["id"] for item in resumes}
    if connection.selected_resume_id not in available:
        connection.selected_resume_id = resumes[0]["id"] if resumes else None
    await session.commit()


def _connection_payload(connection, settings: AppSettings) -> dict:
    if connection is None:
        return {
            "configured": settings.hh_oauth_ready,
            "status": "not_connected",
            "accountName": None,
            "resumes": [],
            "selectedResumeId": None,
            "lastErrorCode": None,
        }
    return {
        "configured": settings.hh_oauth_ready,
        "status": connection.status.value,
        "accountName": (connection.metadata_json or {}).get("name") or None,
        "resumes": (connection.metadata_json or {}).get("resumes", []),
        "selectedResumeId": connection.selected_resume_id,
        "lastErrorCode": connection.last_error_code,
    }
