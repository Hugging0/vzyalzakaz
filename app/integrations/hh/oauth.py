from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlparse

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AppSettings
from app.integrations.hh.client import HHClient
from app.integrations.hh.errors import HHError
from app.models import (
    ExternalConnection,
    ExternalConnectionStatus,
    OAuthState,
    TelegramUser,
)

PROVIDER = "hh"


class TokenCipher:
    def __init__(self, key: str | None):
        if not key:
            raise RuntimeError("HH_TOKEN_ENCRYPTION_KEY is required")
        try:
            self._fernet = Fernet(key.encode())
        except (ValueError, TypeError) as exc:
            raise RuntimeError("HH_TOKEN_ENCRYPTION_KEY must be a Fernet key") from exc

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str | None) -> str:
        if not value:
            raise RuntimeError("Encrypted HH token is missing")
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise RuntimeError("Encrypted HH token cannot be decrypted") from exc


def callback_url(settings: AppSettings) -> str:
    if not settings.public_base_url:
        raise RuntimeError("PUBLIC_BASE_URL is required for HH OAuth")
    base_url = settings.public_base_url.rstrip("/")
    parsed = urlparse(base_url)
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and parsed.hostname not in local_hosts:
        raise RuntimeError("PUBLIC_BASE_URL must use HTTPS for HH OAuth")
    return f"{base_url}/api/integrations/hh/oauth/callback"


async def create_oauth_authorization(
    session: AsyncSession,
    user: TelegramUser,
    settings: AppSettings,
) -> str:
    if not settings.hh_oauth_ready:
        raise RuntimeError("HH OAuth is not configured")
    TokenCipher(settings.hh_token_encryption_key)
    now = datetime.now(UTC)
    await session.execute(delete(OAuthState).where(OAuthState.expires_at <= now))
    state = secrets.token_urlsafe(32)
    session.add(
        OAuthState(
            user_id=user.id,
            provider=PROVIDER,
            state_hash=_hash(state),
            expires_at=now + timedelta(seconds=settings.hh_oauth_state_ttl_seconds),
        )
    )
    await session.commit()
    params = urlencode(
        {
            "response_type": "code",
            "client_id": settings.hh_client_id,
            "redirect_uri": callback_url(settings),
            "state": state,
        }
    )
    return f"{settings.hh_oauth_authorize_url}?{params}"


async def consume_oauth_state(session: AsyncSession, state: str) -> OAuthState:
    record = await session.scalar(
        select(OAuthState).where(
            OAuthState.provider == PROVIDER,
            OAuthState.state_hash == _hash(state),
        )
    )
    now = datetime.now(UTC)
    if record is None or record.used_at is not None or _aware(record.expires_at) <= now:
        raise HHError("oauth_state_invalid", "Ссылка подключения устарела. Начните заново.", 400)
    record.used_at = now
    await session.commit()
    return record


async def finish_oauth(
    session: AsyncSession,
    state: str,
    code: str,
    settings: AppSettings,
    *,
    client: HHClient | None = None,
) -> ExternalConnection:
    state_record = await consume_oauth_state(session, state)
    api = client or HHClient(settings)
    token = await api.exchange_code(code, callback_url(settings))
    access_token = str(token.get("access_token") or "")
    refresh_token = str(token.get("refresh_token") or "")
    if not access_token or not refresh_token:
        raise HHError("auth_required", "HH не вернул токены доступа. Подключите аккаунт снова.", 401)
    me = await api.me(access_token)
    if me.get("is_applicant") is False:
        raise HHError("auth_required", "Подключите аккаунт соискателя HH.", 403)
    connection = await session.scalar(
        select(ExternalConnection).where(
            ExternalConnection.user_id == state_record.user_id,
            ExternalConnection.provider == PROVIDER,
        )
    )
    cipher = TokenCipher(settings.hh_token_encryption_key)
    if connection is None:
        connection = ExternalConnection(user_id=state_record.user_id, provider=PROVIDER)
        session.add(connection)
    connection.external_user_id = str(me.get("id") or "") or None
    connection.access_token_encrypted = cipher.encrypt(access_token)
    connection.refresh_token_encrypted = cipher.encrypt(refresh_token)
    connection.token_expires_at = datetime.now(UTC) + timedelta(seconds=int(token.get("expires_in") or 0))
    connection.status = ExternalConnectionStatus.CONNECTED
    connection.last_error_code = None
    connection.metadata_json = {
        "name": " ".join(value for value in (me.get("first_name"), me.get("last_name")) if value),
    }
    await session.commit()
    await session.refresh(connection)
    return connection


async def access_token_for(
    session: AsyncSession,
    connection: ExternalConnection,
    settings: AppSettings,
    *,
    client: HHClient | None = None,
) -> str:
    if connection.status != ExternalConnectionStatus.CONNECTED:
        raise HHError("auth_required", "Подключите аккаунт HH заново.", 401)
    cipher = TokenCipher(settings.hh_token_encryption_key)
    expires = _aware(connection.token_expires_at) if connection.token_expires_at else None
    if expires and expires > datetime.now(UTC) + timedelta(seconds=60):
        return cipher.decrypt(connection.access_token_encrypted)
    api = client or HHClient(settings)
    try:
        token = await api.refresh_token(cipher.decrypt(connection.refresh_token_encrypted))
    except HHError as exc:
        mark_reauth_required(connection, exc.code)
        await session.commit()
        raise HHError("auth_required", "Подключение HH устарело. Авторизуйтесь снова.", 401) from exc
    access_token = str(token.get("access_token") or "")
    refresh_token = str(token.get("refresh_token") or "")
    if not access_token or not refresh_token:
        mark_reauth_required(connection)
        await session.commit()
        raise HHError("auth_required", "Подключение HH устарело. Авторизуйтесь снова.", 401)
    connection.access_token_encrypted = cipher.encrypt(access_token)
    connection.refresh_token_encrypted = cipher.encrypt(refresh_token)
    connection.token_expires_at = datetime.now(UTC) + timedelta(seconds=int(token.get("expires_in") or 0))
    connection.last_error_code = None
    await session.commit()
    return access_token


def mark_reauth_required(connection: ExternalConnection, error_code: str = "auth_required") -> None:
    connection.status = ExternalConnectionStatus.REAUTH_REQUIRED
    connection.last_error_code = error_code
    connection.access_token_encrypted = None
    connection.refresh_token_encrypted = None
    connection.token_expires_at = None


async def connection_for_user(session: AsyncSession, user_id: int) -> ExternalConnection | None:
    return await session.scalar(
        select(ExternalConnection).where(
            ExternalConnection.user_id == user_id,
            ExternalConnection.provider == PROVIDER,
        )
    )


def resume_payload(item: dict) -> dict:
    status = item.get("status") or {}
    return {
        "id": str(item.get("id") or ""),
        "title": item.get("title") or "Резюме без названия",
        "status": status.get("id") or "unknown",
        "url": item.get("alternate_url"),
        "updatedAt": item.get("updated_at"),
    }


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
