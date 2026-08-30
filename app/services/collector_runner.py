from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.collectors import create_collector
from app.config import SourceConfig
from app.models import CollectorRun, OpportunityStatus
from app.services.pipeline import OpportunityPipeline

logger = logging.getLogger(__name__)


class CollectorRunner:
    def __init__(self, session_factory: async_sessionmaker, pipeline: OpportunityPipeline, notifier=None):
        self.session_factory = session_factory
        self.pipeline = pipeline
        self.notifier = notifier

    async def run(self, config: SourceConfig) -> None:
        async with self.session_factory() as session:
            run = CollectorRun(source=config.name)
            session.add(run)
            await session.commit()
            try:
                items = await create_collector(config).fetch_new()
                created = 0
                merged = 0
                for raw in items:
                    result = await self.pipeline.process(session, raw)
                    created += int(result.created)
                    merged += int(result.merged)
                    opportunity = result.opportunity
                    if result.created and opportunity.status != OpportunityStatus.FILTERED and self.notifier:
                        await self.notifier.notify(opportunity)
                        opportunity.notified_at = datetime.now(UTC)
                run.fetched = len(items)
                run.created = created
                run.merged = merged
                run.finished_at = datetime.now(UTC)
                await session.commit()
            except Exception as exc:
                logger.exception("Collector %s failed", config.name)
                run.error = str(exc)[:2000]
                run.finished_at = datetime.now(UTC)
                await session.commit()
