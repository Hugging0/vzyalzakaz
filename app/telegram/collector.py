from __future__ import annotations

import asyncio
import logging
import re
from contextlib import suppress

from sqlalchemy.ext.asyncio import async_sessionmaker
from telethon import events, utils
from telethon.tl.custom.message import Message

from app.config import AppSettings, SourceConfig
from app.models import OpportunityStatus
from app.schemas import RawOpportunity
from app.services.pipeline import OpportunityPipeline
from app.telegram.client import create_user_client

logger = logging.getLogger(__name__)
URL_RE = re.compile(r"https?://[^\s<>]+")


class TelegramCollector:
    def __init__(
        self,
        settings: AppSettings,
        sources: list[SourceConfig],
        session_factory: async_sessionmaker,
        pipeline: OpportunityPipeline,
        notifier=None,
    ):
        self.settings = settings
        self.sources = [source for source in sources if source.type == "telegram" and source.enabled]
        self.session_factory = session_factory
        self.pipeline = pipeline
        self.notifier = notifier
        self.client = create_user_client(settings)
        self._source_by_chat_id: dict[int, SourceConfig] = {}
        self._initialization_task: asyncio.Task | None = None

    async def start(self) -> bool:
        await self.client.connect()
        if not await self.client.is_user_authorized():
            logger.warning("Telegram user session is not authorized; run: python -m app.telegram_auth")
            await self.client.disconnect()
            return False

        self._initialization_task = asyncio.create_task(
            self._initialize_sources(), name="telegram-source-initialization"
        )
        logger.info("Telegram user session connected; resolving channels in background")
        return True

    async def _initialize_sources(self) -> None:
        entities = []
        for source in self.sources:
            try:
                entity = await self.client.get_entity(source.channel)
                self._source_by_chat_id[utils.get_peer_id(entity)] = source
                entities.append(entity)
            except Exception:
                logger.exception("Cannot resolve Telegram channel %s", source.channel)

        if not entities:
            logger.warning("No Telegram channels could be resolved")
            return
        self.client.add_event_handler(self._on_new_message, events.NewMessage(chats=entities))
        self.client.add_event_handler(self._on_edited_message, events.MessageEdited(chats=entities))
        asyncio.create_task(self._initial_backfill(entities), name="telegram-backfill")
        logger.info("Telegram collector listening to %d channels", len(entities))

    async def stop(self) -> None:
        if self._initialization_task:
            self._initialization_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._initialization_task
        if self.client.is_connected():
            await self.client.disconnect()

    async def _initial_backfill(self, entities: list) -> None:
        for entity in entities:
            source = self._source_by_chat_id.get(utils.get_peer_id(entity))
            if not source:
                continue
            limit = int(source.options.get("backfill_limit", 100))
            try:
                messages = [message async for message in self.client.iter_messages(entity, limit=limit)]
                for message in reversed(messages):
                    if message.message:
                        await self._process_message(message, source)
            except Exception:
                logger.exception("Backfill failed for %s", source.name)

    async def _on_new_message(self, event: events.NewMessage.Event) -> None:
        source = self._source_by_chat_id.get(event.chat_id)
        if source:
            await self._process_message(event.message, source)

    async def _on_edited_message(self, event: events.MessageEdited.Event) -> None:
        source = self._source_by_chat_id.get(event.chat_id)
        if source:
            await self._process_message(event.message, source)

    async def _process_message(self, message: Message, source: SourceConfig) -> None:
        text = message.message or ""
        if not text:
            return
        username = (source.channel or "").lstrip("@")
        url = f"https://t.me/{username}/{message.id}" if username else None
        raw = RawOpportunity(
            source=source.name,
            source_type="telegram",
            external_id=f"{message.chat_id}:{message.id}",
            title=_title(text),
            description=text,
            raw_text=text,
            source_url=url,
            published_at=message.date,
            edited_at=message.edit_date,
            languages=[source.language],
            apply_mode=source.apply_mode,
            metadata={
                "channel_id": message.chat_id,
                "message_id": message.id,
                "links": URL_RE.findall(text),
                "forwarded": bool(message.forward),
            },
        )
        async with self.session_factory() as session:
            result = await self.pipeline.process(session, raw)
            opportunity = result.opportunity
            if result.created and opportunity.status != OpportunityStatus.FILTERED and self.notifier:
                await self.notifier.notify(opportunity)
                opportunity.notified_at = message.date
                await session.commit()


def _title(text: str) -> str:
    for line in text.splitlines():
        cleaned = line.strip(" #*—-\t")
        if len(cleaned) >= 5:
            return cleaned[:180]
    return text[:180]
