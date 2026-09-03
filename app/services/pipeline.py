from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AppSettings
from app.models import (
    ContentCategory,
    Opportunity,
    OpportunityStatus,
    SemanticRepresentation,
    SourceOccurrence,
    UserOpportunity,
)
from app.schemas import RawOpportunity
from app.services.content_classifier import (
    ContentClassification,
    ContentClassifier,
    apply_classification_metadata,
)
from app.services.normalizer import normalize
from app.services.opportunity_facts import FACTS_VERSION, OpportunityFactExtractor

logger = logging.getLogger(__name__)

SUPPLY_CATEGORIES = frozenset(
    {
        ContentCategory.RESUME,
        ContentCategory.JOB_SEEKER,
        ContentCategory.SERVICE_OFFER,
        ContentCategory.AGENCY_OFFER,
        ContentCategory.SELF_PROMOTION,
    }
)
SOURCE_POLICY_REJECT_CATEGORIES = frozenset(
    {
        ContentCategory.ADVERTISEMENT,
        ContentCategory.COURSE_OR_EDUCATION,
        ContentCategory.COMMUNITY_POST,
        ContentCategory.EVENT,
    }
)


@dataclass(slots=True)
class ProcessResult:
    opportunity: Opportunity
    created: bool
    merged: bool = False
    updated: bool = False
    classification: ContentClassification | None = None


class OpportunityPipeline:
    """Persist candidate-neutral opportunities; personalization starts after this service."""

    def __init__(
        self,
        settings: AppSettings,
        classifier: ContentClassifier | None = None,
        fact_extractor: OpportunityFactExtractor | None = None,
    ):
        self.settings = settings
        self.classifier = classifier or ContentClassifier(settings)
        self.fact_extractor = fact_extractor or OpportunityFactExtractor(settings)

    async def process(self, session: AsyncSession, raw: RawOpportunity) -> ProcessResult:
        content = normalize(raw)
        exact = await session.scalar(
            select(Opportunity).where(
                Opportunity.source == raw.source,
                Opportunity.external_id == raw.external_id,
            )
        )
        if exact:
            if raw.edited_at and _is_newer_edit(raw.edited_at, exact.edited_at):
                classification = await self.classifier.classify(raw)
                self._update_content(exact, raw, content)
                await self._classify_extract_and_persist(exact, raw, classification)
                await session.execute(
                    delete(UserOpportunity).where(
                        UserOpportunity.opportunity_id == exact.id,
                        UserOpportunity.status == OpportunityStatus.RECOMMENDED,
                    )
                )
                await session.execute(
                    delete(SemanticRepresentation).where(
                        SemanticRepresentation.entity_type == "opportunity",
                        SemanticRepresentation.entity_key == str(exact.id),
                    )
                )
                await session.commit()
                self._log_classification(raw, classification)
                return ProcessResult(
                    exact,
                    created=False,
                    updated=True,
                    classification=classification,
                )
            return ProcessResult(exact, created=False)

        duplicate = await session.scalar(
            select(Opportunity)
            .where(Opportunity.normalized_hash == content.content_hash)
            .order_by(Opportunity.collected_at.asc())
            .limit(1)
        )
        if duplicate:
            session.add(
                SourceOccurrence(
                    opportunity_id=duplicate.id,
                    source=raw.source,
                    external_id=raw.external_id,
                    source_url=raw.source_url,
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
            return ProcessResult(duplicate, created=False, merged=True)

        classification = await self.classifier.classify(raw)
        opportunity = Opportunity(
            source=raw.source,
            source_type=raw.source_type,
            source_url=raw.source_url,
            external_id=raw.external_id,
            title=raw.title or (raw.description or raw.raw_text)[:140],
            description=raw.description or raw.raw_text,
            company=raw.company,
            client_name=raw.client_name,
            contact_username=content.contact_username,
            contact_email=content.contact_email,
            budget_min=raw.budget_min,
            budget_max=raw.budget_max,
            currency=raw.currency,
            employment_type=raw.employment_type,
            estimated_hours=raw.estimated_hours,
            remote=raw.remote,
            country=raw.country,
            languages=raw.languages,
            skills=raw.skills,
            technologies=raw.technologies,
            published_at=raw.published_at,
            edited_at=raw.edited_at,
            raw_text=raw.raw_text or raw.description,
            normalized_hash=content.content_hash,
            status=OpportunityStatus.NEW,
            apply_mode=raw.apply_mode,
        )
        await self._classify_extract_and_persist(opportunity, raw, classification)
        session.add(opportunity)
        await session.flush()
        session.add(
            SourceOccurrence(
                opportunity_id=opportunity.id,
                source=raw.source,
                external_id=raw.external_id,
                source_url=raw.source_url,
            )
        )
        await session.commit()
        await session.refresh(opportunity)
        self._log_classification(raw, classification)
        return ProcessResult(opportunity, created=True, classification=classification)

    async def _classify_extract_and_persist(
        self,
        opportunity: Opportunity,
        raw: RawOpportunity,
        classification: ContentClassification,
    ) -> None:
        apply_classification_metadata(opportunity, classification)
        rejection = universal_rejection(raw, classification)
        opportunity.status = OpportunityStatus.FILTERED if rejection else OpportunityStatus.NEW
        opportunity.skip_reason = rejection
        facts = await self.fact_extractor.extract(
            raw,
            classification,
            allow_llm=rejection is None,
        )
        opportunity.facts = facts.model_dump(mode="json")
        opportunity.facts_version = FACTS_VERSION

    @staticmethod
    def _update_content(opportunity: Opportunity, raw: RawOpportunity, content) -> None:
        opportunity.title = raw.title or (raw.description or raw.raw_text)[:140]
        opportunity.raw_text = raw.raw_text or raw.description
        opportunity.description = raw.description or raw.raw_text
        opportunity.edited_at = raw.edited_at
        opportunity.normalized_hash = content.content_hash
        opportunity.contact_username = content.contact_username
        opportunity.contact_email = content.contact_email
        for field in (
            "source_url", "company", "client_name", "budget_min", "budget_max", "currency",
            "employment_type", "estimated_hours", "remote", "country", "languages", "skills",
            "technologies", "published_at", "apply_mode",
        ):
            setattr(opportunity, field, getattr(raw, field))

    @staticmethod
    def _log_classification(raw: RawOpportunity, classification: ContentClassification) -> None:
        logger.info(
            "content_classified source=%s external_id=%s category=%s confidence=%.3f "
            "method=%s fallback=%s fallback_failed=%s latency_ms=%.2f accepted=%s",
            raw.source,
            raw.external_id,
            classification.category.value,
            classification.confidence,
            classification.method.value,
            classification.fallback_used,
            classification.fallback_failed,
            classification.latency_ms,
            universal_rejection(raw, classification) is None,
        )


def universal_rejection(raw: RawOpportunity, classification: ContentClassification) -> str | None:
    """Return only source-wide rejection reasons; candidate preferences are forbidden here."""
    if not (raw.raw_text or raw.description or raw.title).strip():
        return "invalid_empty_content"
    if raw.metadata.get("source_policy_violation") is True:
        return "source_policy_violation:explicit"
    category = classification.category
    if category in SUPPLY_CATEGORIES:
        return f"supply_side:{category.value}"
    if category == ContentCategory.SPAM_OR_SCAM and classification.confidence >= 0.85:
        return "spam_or_scam_high_confidence"
    if category in SOURCE_POLICY_REJECT_CATEGORIES:
        return f"source_policy_violation:{category.value}"
    return None


def _is_newer_edit(incoming, stored) -> bool:
    if stored is None:
        return True
    incoming_value = incoming if incoming.tzinfo else incoming.replace(tzinfo=UTC)
    stored_value = stored if stored.tzinfo else stored.replace(tzinfo=UTC)
    return incoming_value > stored_value
