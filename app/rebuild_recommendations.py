from __future__ import annotations

import argparse
import asyncio
from collections import Counter

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import AppSettings, get_settings
from app.database import make_engine
from app.models import (
    ClassificationMethod,
    Opportunity,
    OpportunityStatus,
    TelegramUser,
    UserOpportunity,
)
from app.schemas import RawOpportunity
from app.services.content_classifier import ContentClassification
from app.services.opportunity_facts import FACTS_VERSION, OpportunityFactExtractor
from app.services.pipeline import universal_rejection
from app.services.recommendations import RecommendationService


async def rebuild_recommendations(
    settings: AppSettings,
    *,
    include_fact_llm: bool = False,
) -> Counter[str]:
    """Backfill neutral facts, then rebuild only pending per-user recommendations."""
    engine = make_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    extractor = OpportunityFactExtractor(settings)
    service = RecommendationService(settings, settings.load_profile(), settings.load_portfolio())
    counts: Counter[str] = Counter()
    try:
        async with session_factory() as session:
            opportunities = (await session.scalars(select(Opportunity))).all()
            for opportunity in opportunities:
                raw = _to_raw(opportunity)
                classification = _classification(opportunity)
                facts = await extractor.extract(
                    raw,
                    classification,
                    allow_llm=include_fact_llm,
                )
                opportunity.facts = facts.model_dump(mode="json")
                opportunity.facts_version = FACTS_VERSION
                rejection = universal_rejection(raw, classification)
                opportunity.status = (
                    OpportunityStatus.FILTERED if rejection else OpportunityStatus.NEW
                )
                opportunity.skip_reason = rejection
                _clear_global_personalization(opportunity)
                counts["facts"] += 1
            historical = (
                await session.execute(
                    select(UserOpportunity, TelegramUser, Opportunity)
                    .join(TelegramUser, TelegramUser.id == UserOpportunity.user_id)
                    .join(Opportunity, Opportunity.id == UserOpportunity.opportunity_id)
                    .where(UserOpportunity.status != OpportunityStatus.RECOMMENDED)
                )
            ).all()
            for match, user, opportunity in historical:
                await service.refresh_existing_match(
                    session,
                    user,
                    match,
                    opportunity,
                    allow_llm_rerank=False,
                )
                counts["historical_matches_refreshed"] += 1
            removed = await session.execute(
                delete(UserOpportunity).where(
                    UserOpportunity.status == OpportunityStatus.RECOMMENDED
                )
            )
            counts["pending_matches_removed"] = removed.rowcount or 0
            await session.commit()

            users = (
                await session.scalars(
                    select(TelegramUser).where(TelegramUser.is_active.is_(True))
                )
            ).all()
            for user in users:
                matches = await service.backfill_user(
                    session,
                    user,
                    limit=len(opportunities),
                )
                counts["users"] += 1
                counts["matches"] += len(matches)
    finally:
        await engine.dispose()
    return counts


def _classification(opportunity: Opportunity) -> ContentClassification:
    return ContentClassification(
        category=opportunity.content_category,
        confidence=opportunity.classification_confidence or 0.5,
        method=opportunity.classification_method or ClassificationMethod.DETERMINISTIC,
        reasons=opportunity.classification_reasons or [],
        fallback_used=opportunity.classification_fallback_used,
        fallback_failed=opportunity.classification_fallback_failed,
        latency_ms=opportunity.classification_latency_ms or 0,
        version=opportunity.classification_version or "intent-v1",
    )


def _clear_global_personalization(opportunity: Opportunity) -> None:
    opportunity.prefilter_score = None
    opportunity.prefilter_reasons = []
    opportunity.fit_score = None
    opportunity.money_score = None
    opportunity.win_score = None
    opportunity.freshness_score = None
    opportunity.final_score = None
    opportunity.estimated_effort_hours = None
    opportunity.estimated_effective_hourly_rate = None
    opportunity.analysis = {}
    opportunity.proposal = None
    opportunity.portfolio_item = None


def _to_raw(opportunity: Opportunity) -> RawOpportunity:
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
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild neutral facts and personal recommendations")
    parser.add_argument(
        "--llm-facts",
        action="store_true",
        help="Use the configured LLM for neutral fact extraction",
    )
    args = parser.parse_args()
    counts = asyncio.run(
        rebuild_recommendations(get_settings(), include_fact_llm=args.llm_facts)
    )
    print(" ".join(f"{key}={value}" for key, value in sorted(counts.items())))


if __name__ == "__main__":
    main()
