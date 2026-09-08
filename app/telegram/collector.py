from __future__ import annotations

import asyncio
import logging
import re
from contextlib import suppress
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from telethon import events, utils
from telethon.tl.custom.message import Message

from app.config import AppSettings, SourceConfig
from app.models import CollectorCheckpoint, CollectorRun, OpportunityStatus, SourceOccurrence
from app.schemas import RawOpportunity
from app.services.content_classifier import is_demand_category
from app.services.message_tasks import process_message_tasks
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
        self.sources = [s for s in sources if s.type == "telegram" and s.enabled]
        self.session_factory = session_factory
        self.pipeline = pipeline
        self.notifier = notifier
        self.client = create_user_client(settings)
        self._source_by_chat_id: dict[int, SourceConfig] = {}
        self._initialization_task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self._lock = asyncio.Lock()
        self.last_success_at: datetime | None = None
        self.last_error: str | None = None

    async def start(self) -> bool:
        # A broken proxy must not prevent the web server and HTTP collectors starting.
        self._initialization_task = asyncio.create_task(self._run(), name="telegram-catchup")
        return True

    async def _run(self):
        while True:
            try:
                await asyncio.wait_for(self.client.connect(), timeout=30)
                if not await asyncio.wait_for(self.client.is_user_authorized(), timeout=20):
                    raise RuntimeError("Telegram session is not authorized")
                entities = await self._initialize_sources()
                if not entities:
                    raise RuntimeError("No Telegram channels resolved")
                while self.client.is_connected():
                    self._wake.clear()
                    await self._initial_backfill(entities)
                    try:
                        await asyncio.wait_for(self._wake.wait(), self.settings.telegram_poll_interval)
                    except TimeoutError:
                        pass
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = type(exc).__name__
                logger.exception("Telegram catch-up will retry after connection failure")
            finally:
                await self.client.disconnect()
            await asyncio.sleep(30)

    async def _initialize_sources(self) -> list:
        entities = []
        for source in self.sources:
            try:
                # Cached peer avoids unnecessary ResolveUsername requests and flood waits.
                entity = await asyncio.wait_for(self.client.get_input_entity(source.channel), 30)
                self._source_by_chat_id[utils.get_peer_id(entity)] = source
                entities.append(entity)
            except Exception:
                logger.exception("Cannot resolve Telegram channel %s", source.channel)
        self.client.remove_event_handler(self._on_new_message)
        self.client.remove_event_handler(self._on_edited_message)
        self.client.add_event_handler(self._on_new_message, events.NewMessage(chats=entities))
        self.client.add_event_handler(self._on_edited_message, events.MessageEdited(chats=entities))
        logger.info("Telegram catch-up configured for %d channels", len(entities))
        return entities

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
            if source:
                async with self._lock:
                    await self._poll_source(entity, source)

    async def _poll_source(self, entity, source):
        async with self.session_factory() as session:
            checkpoint = await session.get(CollectorCheckpoint, source.name)
            if checkpoint is None:
                previous = (
                    await session.scalars(
                        select(SourceOccurrence.external_id).where(SourceOccurrence.source == source.name)
                    )
                ).all()
                # Bootstrap once from the pre-migration collector's persisted messages.
                ids = [
                    int(value.split(":")[1])
                    for value in previous
                    if ":" in value and value.split(":")[1].isdigit()
                ]
                checkpoint = CollectorCheckpoint(source=source.name, last_message_id=max(ids, default=0))
                session.add(checkpoint)
            run = CollectorRun(source=source.name)
            session.add(run)
            await session.commit()
            try:
                cursor = checkpoint.last_message_id
                limit = (
                    self.settings.telegram_poll_batch_size
                    if cursor
                    else int(source.options.get("backfill_limit", 30))
                )
                kwargs = {"limit": limit, "min_id": cursor, "reverse": True} if cursor else {"limit": limit}

                async def fetch():
                    return [message async for message in self.client.iter_messages(entity, **kwargs)]

                messages = await asyncio.wait_for(fetch(), timeout=45)
                messages.sort(key=lambda message: message.id)
                run.fetched = len(messages)
                run.created = 0
                for message in messages:
                    if message.message:
                        run.created += await self._process_message(message, source)
                    # Advance only AFTER successful persistence, never from the live event.
                    checkpoint.last_message_id = message.id
                    checkpoint.updated_at = datetime.now(UTC)
                    await session.commit()
                self.last_success_at = datetime.now(UTC)
                self.last_error = None
            except Exception as exc:
                self.last_error = type(exc).__name__
                run.error = type(exc).__name__
                logger.exception("Telegram catch-up failed for %s; position retained", source.name)
            run.finished_at = datetime.now(UTC)
            await session.commit()

    async def _on_new_message(self, event) -> None:
        self._wake.set()

    async def _on_edited_message(self, event) -> None:
        source = self._source_by_chat_id.get(event.chat_id)
        if source:
            async with self._lock:
                await self._process_message(event.message, source)

    async def _process_message(self, message: Message, source: SourceConfig) -> int:
        text = message.message or ""
        if not text:
            return 0
        username = (source.channel or "").lstrip("@")
        raw = RawOpportunity(
            source=source.name,
            source_type="telegram",
            external_id=f"{message.chat_id}:{message.id}",
            title=_title(text),
            description=text,
            raw_text=text,
            source_url=f"https://t.me/{username}/{message.id}" if username else None,
            published_at=message.date,
            edited_at=message.edit_date,
            languages=[source.language],
            apply_mode=source.apply_mode,
            metadata={
                "channel_id": message.chat_id,
                "message_id": message.id,
                "links": URL_RE.findall(text),
                "forwarded": bool(message.forward),
                "source_content_policy": source.content_policy,
                "source_language": source.language,
            },
        )
        async with self.session_factory() as session:
            results = await process_message_tasks(session, self.pipeline, raw)
        for result in results:
            opportunity = result.opportunity
            if (
                (result.created or result.updated)
                and opportunity.status != OpportunityStatus.FILTERED
                and is_demand_category(opportunity.content_category)
                and self.notifier
            ):
                await self.notifier.notify(opportunity)
        return sum(int(result.created) for result in results)


def _title(text: str) -> str:
    for line in text.splitlines():
        cleaned = line.strip(" #*—-\t")
        if len(cleaned) >= 5:
            return cleaned[:180]
    return text[:180]
