from __future__ import annotations

from typing import Any

from telethon import TelegramClient

from app.config import AppSettings


def telegram_proxy(settings: AppSettings) -> dict[str, Any] | None:
    if not settings.telegram_proxy_host:
        return None
    proxy: dict[str, Any] = {
        "proxy_type": "socks5",
        "addr": settings.telegram_proxy_host,
        "port": settings.telegram_proxy_port,
        "rdns": True,
    }
    if settings.telegram_proxy_username:
        proxy["username"] = settings.telegram_proxy_username
    if settings.telegram_proxy_password:
        proxy["password"] = settings.telegram_proxy_password
    return proxy


def create_user_client(settings: AppSettings) -> TelegramClient:
    return TelegramClient(
        settings.telegram_session_path,
        settings.telegram_api_id,
        settings.telegram_api_hash,
        proxy=telegram_proxy(settings),
    )
