from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from datetime import UTC, datetime
from urllib.parse import parse_qsl

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AppSettings, get_settings
from app.database import get_session
from app.models import TelegramUser
from app.services.web_sessions import user_from_web_session

security = HTTPBearer(auto_error=False)


def _secret(settings: AppSettings) -> bytes:
    secret = settings.mini_app_session_secret or settings.telegram_bot_token
    if not secret:
        raise HTTPException(503, "Telegram Mini App authentication is not configured")
    return secret.encode()


def validate_init_data(init_data: str, settings: AppSettings) -> dict:
    if not settings.telegram_bot_token:
        raise HTTPException(503, "Telegram bot is not configured")
    values = dict(parse_qsl(init_data, keep_blank_values=True))
    provided_hash = values.pop("hash", None)
    auth_date = values.get("auth_date")
    if not provided_hash or not auth_date:
        raise HTTPException(401, "Telegram authorization data is incomplete")
    try:
        issued_at = int(auth_date)
    except ValueError as exc:
        raise HTTPException(401, "Telegram authorization timestamp is invalid") from exc
    now = int(datetime.now(UTC).timestamp())
    if issued_at > now + 60 or now - issued_at > settings.mini_app_auth_max_age_seconds:
        raise HTTPException(401, "Telegram authorization has expired")
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    secret_key = hmac.new(b"WebAppData", settings.telegram_bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, provided_hash):
        raise HTTPException(401, "Telegram authorization signature is invalid")
    try:
        user = json.loads(values["user"])
    except (KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(401, "Telegram user data is invalid") from exc
    if not isinstance(user, dict) or not user.get("id"):
        raise HTTPException(401, "Telegram user data is invalid")
    return user


def create_session_token(telegram_user_id: int, settings: AppSettings) -> str:
    expires_at = int(datetime.now(UTC).timestamp()) + settings.mini_app_session_ttl_seconds
    payload = {"sub": telegram_user_id, "exp": expires_at}
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=")
    signature = hmac.new(_secret(settings), encoded, hashlib.sha256).digest()
    return f"{encoded.decode()}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def _decode_session_token(token: str, settings: AppSettings) -> int:
    try:
        encoded, supplied_signature = token.split(".", 1)
        encoded_bytes = encoded.encode()
        expected = hmac.new(_secret(settings), encoded_bytes, hashlib.sha256).digest()
        signature = base64.urlsafe_b64decode(supplied_signature + "=" * (-len(supplied_signature) % 4))
        if not hmac.compare_digest(expected, signature):
            raise ValueError
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if int(payload["exp"]) < int(datetime.now(UTC).timestamp()):
            raise ValueError
        return int(payload["sub"])
    except (binascii.Error, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(401, "Mini App session is invalid or expired") from exc


async def current_mini_app_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: AsyncSession = Depends(get_session),
    settings: AppSettings = Depends(get_settings),
) -> TelegramUser:
    user = None
    if credentials and credentials.scheme.lower() == "bearer":
        telegram_user_id = _decode_session_token(credentials.credentials, settings)
        user = await session.scalar(
            select(TelegramUser).where(TelegramUser.telegram_user_id == telegram_user_id)
        )
    else:
        cookie = request.cookies.get(settings.web_session_cookie_name)
        if cookie:
            user = await user_from_web_session(session, cookie)
    if not user:
        raise HTTPException(401, "Войдите через Telegram, чтобы открыть кабинет")
    return user
