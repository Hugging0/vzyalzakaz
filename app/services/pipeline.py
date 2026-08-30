from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AppSettings, CandidateProfile, PortfolioProject
from app.models import Opportunity, OpportunityStatus, SourceOccurrence
from app.schemas import RawOpportunity
from app.services.normalizer import normalize
from app.services.portfolio import select_portfolio
from app.services.prefilter import evaluate
from app.services.ranking import final_score, freshness_score
from app.services.scoring import OpportunityAnalyzer

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ProcessResult:
    opportunity: Opportunity
    created: bool
    merged: bool = False


class OpportunityPipeline:
    def __init__(
        self,
        settings: AppSettings,
        profile: CandidateProfile,
        portfolio: list[PortfolioProject],
    ):
        self.settings = settings
        self.profile = profile
        self.portfolio = portfolio
        self.analyzer = OpportunityAnalyzer(settings, profile)

    async def process(self, session: AsyncSession, raw: RawOpportunity) -> ProcessResult:
        content = normalize(raw)
        exact = await session.scalar(
            select(Opportunity).where(
                Opportunity.source == raw.source,
                Opportunity.external_id == raw.external_id,
            )
        )
        if exact:
            if raw.edited_at and (not exact.edited_at or raw.edited_at > exact.edited_at):
                exact.raw_text = raw.raw_text or raw.description
                exact.description = raw.description
                exact.edited_at = raw.edited_at
                await session.commit()
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

        prefilter = evaluate(raw, self.profile)
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
            prefilter_score=prefilter.score,
            prefilter_reasons=prefilter.reasons,
            status=OpportunityStatus.NEW if prefilter.passed else OpportunityStatus.FILTERED,
            apply_mode=raw.apply_mode,
        )
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

        if prefilter.passed:
            matched_portfolio = select_portfolio(
                f"{raw.title} {raw.description} {raw.raw_text}", self.portfolio
            )
            analysis = await self.analyzer.analyze(raw, matched_portfolio)
            fresh = freshness_score(raw.published_at)
            score = final_score(
                analysis.fit_score,
                analysis.money_score,
                analysis.win_score,
                fresh,
                self.profile.ranking,
            )
            opportunity.analysis = analysis.model_dump()
            opportunity.fit_score = analysis.fit_score
            opportunity.money_score = analysis.money_score
            opportunity.win_score = analysis.win_score
            opportunity.freshness_score = fresh
            opportunity.final_score = score
            opportunity.estimated_effort_hours = analysis.estimated_hours or None
            expected = raw.budget_max or raw.budget_min
            if expected and analysis.estimated_hours and raw.currency == "RUB":
                opportunity.estimated_effective_hourly_rate = round(expected / analysis.estimated_hours, 2)
            opportunity.portfolio_item = matched_portfolio.slug if matched_portfolio else None
            if score >= self.profile.ranking.digest_threshold:
                opportunity.status = OpportunityStatus.RECOMMENDED

        await session.commit()
        await session.refresh(opportunity)
        return ProcessResult(opportunity, created=True)

    async def generate_proposal(self, session: AsyncSession, opportunity: Opportunity) -> str:
        portfolio = next((item for item in self.portfolio if item.slug == opportunity.portfolio_item), None)
        raw = RawOpportunity(
            source=opportunity.source,
            source_type=opportunity.source_type,
            external_id=opportunity.external_id,
            title=opportunity.title,
            description=opportunity.description,
            raw_text=opportunity.raw_text,
            source_url=opportunity.source_url,
            client_name=opportunity.client_name,
            contact_username=opportunity.contact_username,
            budget_min=opportunity.budget_min,
            budget_max=opportunity.budget_max,
            currency=opportunity.currency,
            apply_mode=opportunity.apply_mode,
        )
        proposal = await self.analyzer.generate_proposal(raw, opportunity.analysis, portfolio)
        opportunity.proposal = proposal
        opportunity.status = OpportunityStatus.APPROVED
        opportunity.approved_at = datetime.now(UTC)
        await session.commit()
        return proposal
