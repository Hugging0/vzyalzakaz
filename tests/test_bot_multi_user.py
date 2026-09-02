import hashlib
import hmac
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import make_engine
from app.mini_app_api import TelegramAuthRequest, mini_app_auth
from app.models import Base, TelegramUser
from app.services.recommendations import RecommendationService
from app.telegram.bot import TelegramBot


@pytest.mark.asyncio
async def test_bot_registers_and_updates_users_independently(settings, profile):
    settings = settings.model_copy(update={"mini_app_url": "https://example.com/app"})
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    recommendations = RecommendationService(settings, profile, settings.load_portfolio())
    bot = TelegramBot(settings, session_factory, recommendations)
    sent = []

    async def fake_send(chat_id, text, keyboard=None):
        sent.append((chat_id, text, keyboard))
        return {}

    bot._send_message = fake_send
    await bot._handle_update(_message(3001, "/start", "Alice"))
    await bot._handle_update(_message(3002, "/start", "Bob"))
    await bot._handle_update(_message(3001, "/skills Python, FastAPI", "Alice"))

    async with session_factory() as session:
        users = (await session.scalars(select(TelegramUser).order_by(TelegramUser.id))).all()

    assert len(users) == 2
    assert recommendations.profile_for(users[0]).candidate.skills == ["Python", "FastAPI"]
    assert recommendations.profile_for(users[1]).candidate.skills == []
    assert {chat_id for chat_id, _, _ in sent} == {3001, 3002}
    assert sent[0][2] == [
        [
            {
                "text": "Рассказать о себе",
                "callback_data": "intake:start",
                "style": "primary",
            }
        ],
        [
            {
                "text": "Заполнить в кабинете",
                "web_app": {"url": "https://example.com/app/profile"},
                "style": "primary",
            }
        ],
    ]
    await engine.dispose()


@pytest.mark.asyncio
async def test_bot_accepts_one_freeform_profile_message(settings, profile):
    settings = settings.model_copy(update={"mini_app_url": "https://example.com/app"})
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    recommendations = RecommendationService(settings, profile, settings.load_portfolio())
    bot = TelegramBot(settings, session_factory, recommendations)
    sent = []

    async def fake_send(chat_id, text, keyboard=None):
        sent.append((chat_id, text, keyboard))
        return {}

    async def fake_api(method, payload, timeout=20):
        return True

    bot._send_message = fake_send
    bot._api = fake_api
    await bot._handle_update(_message(3010, "/start", "Маша"))
    await bot._handle_update(
        _message(
            3010,
            "Проектирую интерфейсы в Figma и занимаюсь UI/UX. Ищу проекты от 50 000 ₽.",
            "Маша",
        )
    )

    async with session_factory() as session:
        user = await recommendations.get_user(session, 3010)
        candidate = recommendations.profile_for(user).candidate
        assert user.profile["ui"]["onboarding_completed"] is True
        assert {"Figma", "UI/UX"}.issubset(candidate.skills)
        assert "Проектирую интерфейсы" in candidate.about
    assert "Профиль готов" in sent[-1][1]
    await engine.dispose()


@pytest.mark.asyncio
async def test_registration_policy_is_shared_between_bot_and_mini_app(settings, profile):
    settings = settings.model_copy(
        update={
            "registration_mode": "invite",
            "registration_invite_code": "valid-invite",
            "telegram_owner_id": 7001,
        }
    )
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    recommendations = RecommendationService(settings, profile, settings.load_portfolio())

    async with session_factory() as session:
        assert await recommendations.can_register(session, 7001)
        assert not await recommendations.can_register(session, 7002)
        assert await recommendations.can_register(session, 7002, "valid-invite")

    await engine.dispose()


@pytest.mark.asyncio
async def test_mini_app_auth_registers_verified_telegram_user(settings, profile):
    settings = settings.model_copy(
        update={
            "telegram_bot_token": "123456:test-token",
            "mini_app_session_secret": "test-session-secret",
            "registration_mode": "open",
        }
    )
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    recommendations = RecommendationService(settings, profile, settings.load_portfolio())
    runtime = SimpleNamespace(
        settings=settings,
        session_factory=session_factory,
        recommendations=recommendations,
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=runtime)))
    init_data = _signed_init_data(settings.telegram_bot_token, 8001)

    response = await mini_app_auth(TelegramAuthRequest(init_data=init_data), request)

    async with session_factory() as session:
        user = await recommendations.get_user(session, 8001)
    assert response["token"]
    assert user is not None
    assert user.first_name == "Новый пользователь"
    await engine.dispose()


def _message(user_id: int, text: str, first_name: str) -> dict:
    return {
        "message": {
            "from": {
                "id": user_id,
                "first_name": first_name,
                "username": first_name.lower(),
                "language_code": "en",
            },
            "chat": {"id": user_id, "type": "private"},
            "text": text,
        }
    }


def _signed_init_data(bot_token: str, user_id: int) -> str:
    values = {
        "auth_date": str(int(datetime.now(UTC).timestamp())),
        "query_id": "test-query",
        "user": json.dumps(
            {"id": user_id, "first_name": "Новый пользователь", "language_code": "ru"},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    return urlencode(values)
