"""Bounded, source-balanced warming of the shared active-corpus embedding cache."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select

from app.models import Opportunity, OpportunityStatus
from app.services.content_classifier import DEMAND_CATEGORIES
from app.services.retrieval import balanced_indices, opportunity_retrieval_text

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
        _, hits = await retriever._opportunity_vectors(
            session,
            [str(row.id) for row in rows],
            [opportunity_retrieval_text(facts) for _, facts in candidates],
            [row.facts_version for row in rows],
            max_new=settings.semantic_index_batch_size,
            priority=balanced_indices(candidates),
        )
        await session.commit()
        result = {
            "corpus": len(rows),
            "cache_hits": hits,
            "indexed": min(len(rows) - hits, settings.semantic_index_batch_size),
        }
        logger.info("semantic_index_batch %s", result)
        return result
