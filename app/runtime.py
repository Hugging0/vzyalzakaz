from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import AppSettings
from app.services.collector_runner import CollectorRunner
from app.services.pipeline import OpportunityPipeline
from app.services.recommendations import RecommendationService
from app.telegram.bot import TelegramBot
from app.telegram.collector import TelegramCollector

logger = logging.getLogger(__name__)


class Runtime:
    def __init__(self, settings: AppSettings, session_factory: async_sessionmaker):
        self.settings = settings
        self.session_factory = session_factory
        self.profile = settings.load_profile()
        self.sources = [source for source in settings.load_sources() if source.enabled]
        self.portfolio = settings.load_portfolio()
        self.pipeline = OpportunityPipeline(settings, self.profile, self.portfolio)
        self.recommendations = RecommendationService(settings, self.profile, self.portfolio)
        self.telegram_bot: TelegramBot | None = None
        self.telegram_collector: TelegramCollector | None = None
        self.scheduler: AsyncIOScheduler | None = None
        self.collector_runner = CollectorRunner(session_factory, self.pipeline)

    async def start(self) -> None:
        telegram_sources = [source for source in self.sources if source.type == "telegram"]
        if self.settings.enable_telegram_collector and self.settings.telegram_user_ready:
            self.telegram_collector = TelegramCollector(
                self.settings,
                telegram_sources,
                self.session_factory,
                self.pipeline,
            )
        if self.settings.enable_telegram_bot and self.settings.telegram_bot_ready:
            self.telegram_bot = TelegramBot(self.settings, self.session_factory, self.recommendations)
            await self.telegram_bot.start()
        if self.telegram_collector:
            self.telegram_collector.notifier = self.telegram_bot
            started = await self.telegram_collector.start()
            if not started:
                self.telegram_collector = None
        self.collector_runner.notifier = self.telegram_bot

        if self.settings.enable_scheduler:
            self.scheduler = AsyncIOScheduler(timezone="UTC")
            web_sources = [source for source in self.sources if source.type != "telegram"]
            for index, source in enumerate(web_sources):
                if source.type == "telegram":
                    continue
                self.scheduler.add_job(
                    self.collector_runner.run,
                    "interval",
                    seconds=max(60, source.poll_interval),
                    args=[source],
                    id=f"source:{source.name}",
                    name=f"Collect {source.name}",
                    max_instances=1,
                    coalesce=True,
                    next_run_time=datetime.now(UTC) + timedelta(seconds=index * 5),
                )
            self.scheduler.start()
            logger.info("Scheduler configured with %d web sources", len(self.scheduler.get_jobs()))

    async def stop(self) -> None:
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        if self.telegram_bot:
            await self.telegram_bot.stop()
        if self.telegram_collector:
            await self.telegram_collector.stop()
