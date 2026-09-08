"""Retry source content that was stranded as unknown during provider outages."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import ContentCategory, Opportunity, OpportunityStatus
from app.reclassify_content import _to_raw
from app.services.content_classifier import apply_classification_metadata
from app.services.opportunity_facts import FACTS_VERSION
from app.services.pipeline import universal_rejection


async def recover_unknown_content(session_factory, pipeline, batch_size=8):
    settings = pipeline.settings
    if not pipeline.fact_extractor.client.available:
        return {"processed": 0}
    sources = {s.name: s for s in settings.load_sources() if s.enabled and s.language in {"ru", "multi"}}
    marker = f"recovery-v1:{settings.llm_model}"
    cutoff = datetime.now(UTC) - timedelta(days=settings.matching_corpus_days)
    count = 0
    async with session_factory() as session:
        rows = (
            await session.scalars(
                select(Opportunity)
                .where(
                    Opportunity.content_category == ContentCategory.UNKNOWN,
                    Opportunity.status != OpportunityStatus.FILTERED,
                    Opportunity.source.in_(sources),
                    Opportunity.published_at >= cutoff,
                )
                .order_by(Opportunity.published_at.desc())
            )
        ).all()
        for row in rows:
            if marker in (row.classification_reasons or []):
                continue
            raw = _to_raw(row, sources[row.source].content_policy)
            classification = await pipeline.classifier.classify(raw)
            if classification.fallback_failed:
                break  # Do not hammer an unavailable/billing-blocked provider.
            apply_classification_metadata(row, classification)
            row.classification_reasons = [*(row.classification_reasons or []), marker]
            facts = await pipeline.fact_extractor.extract(raw, classification)
            row.facts = facts.model_dump(mode="json")
            row.facts_version = FACTS_VERSION
            rejection = universal_rejection(raw, classification)
            row.status = OpportunityStatus.FILTERED if rejection else OpportunityStatus.NEW
            row.skip_reason = rejection
            await session.commit()
            count += 1
            if count >= batch_size:
                break
    return {"processed": count}
