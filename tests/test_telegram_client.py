from __future__ import annotations

from app.config import AppSettings
from app.telegram.client import telegram_proxy


def test_telegram_proxy_is_disabled_without_host() -> None:
    settings = AppSettings(_env_file=None)

    assert telegram_proxy(settings) is None


def test_telegram_proxy_uses_authenticated_socks5() -> None:
    settings = AppSettings(
        _env_file=None,
        telegram_proxy_host="proxy.example.com",
        telegram_proxy_port=1081,
        telegram_proxy_username="huntagent",
        telegram_proxy_password="secret",
    )

    assert telegram_proxy(settings) == {
        "proxy_type": "socks5",
        "addr": "proxy.example.com",
        "port": 1081,
        "username": "huntagent",
        "password": "secret",
        "rdns": True,
    }
