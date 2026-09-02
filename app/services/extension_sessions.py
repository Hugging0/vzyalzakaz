from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AppSettings
from app.models import ExtensionInstallation, ExtensionLinkTicket, TelegramUser


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def create_extension_link_ticket(
    session: AsyncSession,
    user: TelegramUser,
    settings: AppSettings,
) -> tuple[str, ExtensionLinkTicket]:
    code = secrets.token_urlsafe(18)
    ticket = ExtensionLinkTicket(
        user_id=user.id,
        code_hash=_hash_secret(code),
        expires_at=datetime.now(UTC)
        + timedelta(seconds=settings.extension_link_ticket_ttl_seconds),
    )
    session.add(ticket)
    await session.commit()
    await session.refresh(ticket)
    return code, ticket


async def exchange_extension_link_ticket(
    session: AsyncSession,
    code: str,
    installation_id: str,
    browser: str,
    version: str,
    settings: AppSettings,
) -> tuple[ExtensionInstallation, str]:
    now = datetime.now(UTC)
    ticket = await session.scalar(
        select(ExtensionLinkTicket)
        .where(ExtensionLinkTicket.code_hash == _hash_secret(code))
        .with_for_update()
    )
    if (
        ticket is None
        or ticket.used_at is not None
        or _as_utc(ticket.expires_at) <= now
    ):
        raise HTTPException(401, "Код подключения недействителен или уже использован")

    user = await session.get(TelegramUser, ticket.user_id)
    if user is None:
        raise HTTPException(401, "Аккаунт подключения больше недоступен")

    token = secrets.token_urlsafe(32)
    installation = await session.scalar(
        select(ExtensionInstallation).where(
            ExtensionInstallation.user_id == user.id,
            ExtensionInstallation.installation_id == installation_id,
        )
    )
    expires_at = now + timedelta(seconds=settings.extension_session_ttl_seconds)
    if installation is None:
        installation = ExtensionInstallation(
            user_id=user.id,
            installation_id=installation_id,
            token_hash=_hash_secret(token),
            browser=browser,
            version=version,
            expires_at=expires_at,
            last_seen_at=now,
        )
        session.add(installation)
    else:
        installation.token_hash = _hash_secret(token)
        installation.browser = browser
        installation.version = version
        installation.expires_at = expires_at
        installation.revoked_at = None
        installation.last_seen_at = now
        installation.last_error_code = None
    ticket.used_at = now
    await session.commit()
    await session.refresh(installation)
    return installation, token


async def extension_from_token(
    session: AsyncSession,
    token: str,
) -> ExtensionInstallation | None:
    installation = await session.scalar(
        select(ExtensionInstallation).where(
            ExtensionInstallation.token_hash == _hash_secret(token),
            ExtensionInstallation.revoked_at.is_(None),
        )
    )
    if installation is None or _as_utc(installation.expires_at) <= datetime.now(UTC):
        return None
    return installation


async def revoke_extension_installation(
    session: AsyncSession,
    user: TelegramUser,
    installation_id: UUID,
) -> None:
    installation = await session.scalar(
        select(ExtensionInstallation).where(
            ExtensionInstallation.id == installation_id,
            ExtensionInstallation.user_id == user.id,
            ExtensionInstallation.revoked_at.is_(None),
        )
    )
    if installation is None:
        raise HTTPException(404, "Подключение расширения не найдено")
    installation.revoked_at = datetime.now(UTC)
    await session.commit()
