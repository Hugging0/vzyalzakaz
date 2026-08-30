import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import make_engine
from app.models import Base, TelegramUser
from app.services.recommendations import RecommendationService
from app.telegram.bot import TelegramBot


@pytest.mark.asyncio
async def test_bot_registers_and_updates_users_independently(settings, profile):
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
