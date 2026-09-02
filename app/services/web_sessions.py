from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Response
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AppSettings
from app.models import TelegramUser, WebLoginTicket, WebSession


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_login_ticket(
    session: AsyncSession,
    user: TelegramUser,
    settings: AppSettings,
) -> str:
    now = datetime.now(UTC)
    await session.execute(
        delete(WebLoginTicket).where(
            or_(WebLoginTicket.expires_at <= now, WebLoginTicket.used_at.is_not(None))
        )
    )
    token = secrets.token_urlsafe(32)
    session.add(
        WebLoginTicket(
            user_id=user.id,
            token_hash=_token_hash(token),
            expires_at=now + timedelta(seconds=settings.web_login_ticket_ttl_seconds),
        )
    )
    await session.commit()
    return token


async def exchange_login_ticket(
    session: AsyncSession,
    token: str,
    settings: AppSettings,
) -> tuple[TelegramUser, str]:
    now = datetime.now(UTC)
    ticket = await session.scalar(
        select(WebLoginTicket).where(
            WebLoginTicket.token_hash == _token_hash(token),
            WebLoginTicket.used_at.is_(None),
            WebLoginTicket.expires_at > now,
        )
    )
    if not ticket:
        raise HTTPException(401, "Ссылка для входа недействительна или уже использована")
    user = await session.get(TelegramUser, ticket.user_id)
    if not user:
        raise HTTPException(401, "Пользователь больше не существует")
    ticket.used_at = now
    raw_session = await create_web_session(session, user, settings, commit=False)
    await session.commit()
    return user, raw_session


async def create_web_session(
    session: AsyncSession,
    user: TelegramUser,
    settings: AppSettings,
    *,
    commit: bool = True,
) -> str:
    now = datetime.now(UTC)
    await session.execute(delete(WebSession).where(WebSession.expires_at <= now))
    token = secrets.token_urlsafe(48)
    session.add(
        WebSession(
            user_id=user.id,
            token_hash=_token_hash(token),
            expires_at=now + timedelta(seconds=settings.web_session_ttl_seconds),
        )
    )
    if commit:
        await session.commit()
    return token


async def user_from_web_session(
    session: AsyncSession,
    token: str,
) -> TelegramUser | None:
    now = datetime.now(UTC)
    row = (
        await session.execute(
            select(WebSession, TelegramUser)
            .join(TelegramUser, TelegramUser.id == WebSession.user_id)
            .where(
                WebSession.token_hash == _token_hash(token),
                WebSession.expires_at > now,
            )
        )
    ).one_or_none()
    if not row:
        return None
    web_session, user = row
    web_session.last_seen_at = now
    await session.commit()
    return user


async def revoke_web_session(session: AsyncSession, token: str | None) -> None:
    if not token:
        return
    web_session = await session.scalar(
        select(WebSession).where(WebSession.token_hash == _token_hash(token))
    )
    if web_session:
        await session.delete(web_session)
        await session.commit()


def set_session_cookie(response: Response, token: str, settings: AppSettings) -> None:
    secure = _secure_cookie(settings)
    response.set_cookie(
        key=settings.web_session_cookie_name,
        value=token,
        max_age=settings.web_session_ttl_seconds,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, settings: AppSettings) -> None:
    response.delete_cookie(
        key=settings.web_session_cookie_name,
        httponly=True,
        secure=_secure_cookie(settings),
        samesite="lax",
        path="/",
    )


def _secure_cookie(settings: AppSettings) -> bool:
    return any(
        value and value.startswith("https://")
        for value in (settings.public_base_url, settings.mini_app_url)
    )
