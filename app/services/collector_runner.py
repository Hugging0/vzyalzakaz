from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.collectors import create_collector
from app.config import SourceConfig
from app.models import CollectorRun, OpportunityStatus
from app.services.content_classifier import is_demand_category
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
            run_id = run.id
            try:
                items = await create_collector(config).fetch_new()
                created = 0
                merged = 0
                classifications: Counter[str] = Counter()
                classification_latency_ms = 0.0
                semantic_fallback_count = 0
                semantic_fallback_failures = 0
                item_errors: list[str] = []
                for raw in items:
                    raw.metadata.setdefault("source_content_policy", config.content_policy)
                    raw.metadata.setdefault("source_language", config.language)
                    try:
                        result = await self.pipeline.process(session, raw)
                    except Exception as exc:
                        await session.rollback()
                        logger.exception(
                            "Collector %s skipped malformed item %s",
                            config.name,
                            raw.external_id,
                        )
                        item_errors.append(f"{raw.external_id}: {exc}")
                        continue
                    created += int(result.created)
                    merged += int(result.merged)
                    if result.created and result.classification:
                        classifications[result.classification.category.value] += 1
                        classification_latency_ms += result.classification.latency_ms
                        semantic_fallback_count += int(result.classification.fallback_used)
                        semantic_fallback_failures += int(result.classification.fallback_failed)
                    opportunity = result.opportunity
                    if (
                        (result.created or result.updated)
                        and opportunity.status != OpportunityStatus.FILTERED
                        and is_demand_category(opportunity.content_category)
                        and self.notifier
                    ):
                        await self.notifier.notify(opportunity)
                run = await session.get(CollectorRun, run_id)
                run.fetched = len(items)
                run.created = created
                run.merged = merged
                run.classification_counts = dict(classifications)
                run.semantic_fallback_count = semantic_fallback_count
                run.semantic_fallback_failures = semantic_fallback_failures
                run.classification_latency_ms = round(
                    classification_latency_ms / max(sum(classifications.values()), 1),
                    2,
                )
                run.error = "\n".join(item_errors)[:2000] or None
                run.finished_at = datetime.now(UTC)
                await session.commit()
                logger.info(
                    "content_classification_summary source=%s classified=%d accepted=%d "
                    "fallback=%d fallback_failures=%d avg_latency_ms=%.2f categories=%s",
                    config.name,
                    sum(classifications.values()),
                    sum(classifications.get(category, 0) for category in ("project", "job", "gig")),
                    semantic_fallback_count,
                    semantic_fallback_failures,
                    run.classification_latency_ms,
                    dict(classifications),
                )
            except Exception as exc:
                logger.exception("Collector %s failed", config.name)
                await session.rollback()
                run = await session.get(CollectorRun, run_id)
                run.error = str(exc)[:2000]
                run.finished_at = datetime.now(UTC)
                await session.commit()
