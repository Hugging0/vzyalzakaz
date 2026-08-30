from __future__ import annotations

from pathlib import Path

import pytest

from app.config import AppSettings


@pytest.fixture
def settings() -> AppSettings:
    return AppSettings(
        database_url="sqlite+aiosqlite:///:memory:",
        config_dir=Path("config"),
        llm_provider="disabled",
        enable_scheduler=False,
        enable_telegram_collector=False,
        enable_telegram_bot=False,
    )


@pytest.fixture
def profile(settings):
    return settings.load_profile()
