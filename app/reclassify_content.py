from __future__ import annotations

import argparse
import asyncio
from collections import Counter

from sqlalchemy import or_, select, update

from app.config import AppSettings, get_settings
from app.database import make_engine
from app.models import Opportunity, OpportunityStatus, UserOpportunity
from app.schemas import RawOpportunity
from app.services.content_classifier import (
    CLASSIFICATION_VERSION,
    ContentClassifier,
    apply_classification_metadata,
)
from app.services.opportunity_facts import FACTS_VERSION, OpportunityFactExtractor
from app.services.pipeline import universal_rejection


async def reclassify_legacy_rows(
    settings: AppSettings,
    *,
    include_semantic: bool = False,
    limit: int | None = None,
) -> Counter[str]:
    """Classify legacy rows and persist neutral facts under the current global policy."""
    classifier_settings = settings
    if not include_semantic:
        classifier_settings = settings.model_copy(update={"intent_classifier_enabled": False})
    classifier = ContentClassifier(classifier_settings)
    fact_extractor = OpportunityFactExtractor(classifier_settings)
    source_policies = {source.name: source.content_policy for source in settings.load_sources()}
    engine = make_engine(settings.database_url)
    counts: Counter[str] = Counter()
    try:
        from sqlalchemy.ext.asyncio import async_sessionmaker

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            query = (
                select(Opportunity)
                .where(
                    or_(
                        Opportunity.classification_version.is_(None),
                        Opportunity.classification_version != CLASSIFICATION_VERSION,
                    )
                )
                .order_by(Opportunity.collected_at.asc())
            )
            if limit is not None:
                query = query.limit(limit)
            opportunities = (await session.scalars(query)).all()
            for opportunity in opportunities:
                raw = _to_raw(
                    opportunity,
                    source_policies.get(opportunity.source, "mixed"),
                )
                classification = await classifier.classify(raw)
                apply_classification_metadata(opportunity, classification)
                facts = await fact_extractor.extract(
                    raw,
                    classification,
                    allow_llm=include_semantic,
                )
                opportunity.facts = facts.model_dump(mode="json")
                opportunity.facts_version = FACTS_VERSION
                counts[classification.category.value] += 1
                counts["semantic_fallback"] += int(classification.fallback_used)
                counts["semantic_failure"] += int(classification.fallback_failed)
                rejection = universal_rejection(raw, classification)
                opportunity.skip_reason = rejection
                if rejection:
                    opportunity.status = OpportunityStatus.FILTERED
                    await session.execute(
                        update(UserOpportunity)
                        .where(
                            UserOpportunity.opportunity_id == opportunity.id,
                            UserOpportunity.status == OpportunityStatus.RECOMMENDED,
                        )
                        .values(status=OpportunityStatus.FILTERED)
                    )
                elif opportunity.status == OpportunityStatus.FILTERED:
                    opportunity.status = OpportunityStatus.NEW
            await session.commit()
    finally:
        await engine.dispose()
    return counts


def _to_raw(opportunity: Opportunity, source_policy: str) -> RawOpportunity:
    return RawOpportunity(
        source=opportunity.source,
        source_type=opportunity.source_type,
        external_id=opportunity.external_id,
        title=opportunity.title,
        description=opportunity.description,
        raw_text=opportunity.raw_text,
        source_url=opportunity.source_url,
        company=opportunity.company,
        client_name=opportunity.client_name,
        contact_username=opportunity.contact_username,
        contact_email=opportunity.contact_email,
        budget_min=opportunity.budget_min,
        budget_max=opportunity.budget_max,
        currency=opportunity.currency,
        employment_type=opportunity.employment_type,
        estimated_hours=opportunity.estimated_hours,
        remote=opportunity.remote,
        country=opportunity.country,
        languages=opportunity.languages,
        skills=opportunity.skills,
        technologies=opportunity.technologies,
        published_at=opportunity.published_at,
        edited_at=opportunity.edited_at,
        apply_mode=opportunity.apply_mode,
        metadata={"source_content_policy": source_policy},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify legacy opportunity rows")
    parser.add_argument("--semantic", action="store_true", help="Use LLM for ambiguous rows")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    counts = asyncio.run(
        reclassify_legacy_rows(
            get_settings(),
            include_semantic=args.semantic,
            limit=args.limit,
        )
    )
    print(" ".join(f"{key}={value}" for key, value in sorted(counts.items())))


if __name__ == "__main__":
    main()
