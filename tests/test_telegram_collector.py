from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telethon import utils
from telethon.tl.types import PeerChannel

from app.config import SourceConfig
from app.telegram.collector import TelegramCollector


class FakeTelegramClient:
    def iter_messages(self, entity, limit):
        async def messages():
            yield SimpleNamespace(message="Python freelance project")

        return messages()


@pytest.mark.asyncio
async def test_backfill_uses_normalized_channel_peer_id() -> None:
    entity = PeerChannel(channel_id=123456)
    source = SourceConfig(
        name="telegram_python_jobs",
        type="telegram",
        collector="telethon",
        channel="@python_jobs",
        options={"backfill_limit": 10},
    )
    collector = object.__new__(TelegramCollector)
    collector.client = FakeTelegramClient()
    collector._source_by_chat_id = {utils.get_peer_id(entity): source}
    collector._process_message = AsyncMock()

    await collector._initial_backfill([entity])

    collector._process_message.assert_awaited_once()
    assert collector._process_message.await_args.args[1] is source
