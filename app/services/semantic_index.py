"""Bounded, source-balanced warming of the shared active-corpus embedding cache."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select

from app.models import Opportunity, OpportunityStatus
from app.services.content_classifier import DEMAND_CATEGORIES
from app.services.embeddings import EmbeddingError
from app.services.retrieval import balanced_indices, opportunity_retrieval_text, text_hash

logger = logging.getLogger(__name__)


async def index_active_corpus(session_factory, recommendations) -> dict:
    settings = recommendations.settings
    retriever = recommendations.retriever
    if not retriever.provider.available:
        return {"indexed": 0, "disabled": True}
    cutoff = datetime.now(UTC) - timedelta(days=settings.matching_corpus_days)
    async with session_factory() as session:
        rows = list(
            (
                await session.scalars(
                    select(Opportunity)
                    .where(
                        Opportunity.status != OpportunityStatus.FILTERED,
                        Opportunity.content_category.in_(DEMAND_CATEGORIES),
                        or_(
                            Opportunity.published_at >= cutoff,
                            Opportunity.published_at.is_(None) & (Opportunity.collected_at >= cutoff),
                        ),
                    )
                    .order_by(Opportunity.published_at.desc().nullslast(), Opportunity.id)
                )
            ).all()
        )
        candidates = [(row, await recommendations._facts_for(session, row)) for row in rows]
        await session.commit()
        keys = [str(row.id) for row in rows]
        texts = [opportunity_retrieval_text(facts) for _, facts in candidates]
        versions = [row.facts_version for row in rows]
        vectors, hits = await retriever._opportunity_vectors(
            session,
            keys,
            texts,
            versions,
            max_new=0,
        )
        now = datetime.now(UTC)
        backoff = {
            key: until for key, until in getattr(retriever, "index_retry_after", {}).items() if until > now
        }
        retriever.index_retry_after = backoff
        indexed = failed = attempted = consecutive_failures = 0
        for index in balanced_indices(candidates):
            retry_key = f"{keys[index]}:{text_hash(texts[index])}"
            if vectors[index] is not None or retry_key in backoff:
                continue
            if attempted >= settings.semantic_index_batch_size:
                break
            attempted += 1
            try:
                # Persist each success before moving on: one rejected input or
                # transient upstream error must not discard a whole paid batch.
                await retriever._opportunity_vectors(
                    session,
                    [keys[index]],
                    [texts[index]],
                    [versions[index]],
                    max_new=1,
                )
                await session.commit()
                indexed += 1
                consecutive_failures = 0
            except EmbeddingError:
                await session.rollback()
                failed += 1
                consecutive_failures += 1
                backoff[retry_key] = datetime.now(UTC) + timedelta(minutes=15)
                logger.warning("semantic_index_item_failed opportunity=%s retry_minutes=15", keys[index])
                if consecutive_failures >= 3:
                    break  # Provider-wide outage: do not send the remaining batch.
        result = {
            "corpus": len(rows),
            "cache_hits": hits,
            "indexed": indexed,
            "attempted": attempted,
            "failed": failed,
            "backoff": len(backoff),
        }
        logger.info("semantic_index_batch %s", result)
        return result
