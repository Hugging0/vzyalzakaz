from __future__ import annotations

import logging
from datetime import UTC, datetime
from time import perf_counter

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AppSettings, Candidate, CandidateProfile, PortfolioProject
from app.models import (
    ClassificationMethod,
    Opportunity,
    OpportunityStatus,
    TelegramUser,
    UserOpportunity,
)
from app.schemas import OpportunityFacts, RawOpportunity, UserMatchAnalysis
from app.services.content_classifier import (
    DEMAND_CATEGORIES,
    ContentClassification,
    is_demand_category,
)
from app.services.matching import UserMatchAnalyzer
from app.services.opportunity_facts import FACTS_VERSION, OpportunityFactExtractor
from app.services.portfolio import select_portfolio
from app.services.retrieval import CandidateRetriever, RetrievalCandidate
from app.services.scoring import CandidateAssistant

logger = logging.getLogger(__name__)


class RecommendationService:
    """Builds user-specific matches from globally persisted, candidate-neutral facts."""

    def __init__(
        self,
        settings: AppSettings,
        default_profile: CandidateProfile,
        default_portfolio: list[PortfolioProject],
        retriever: CandidateRetriever | None = None,
    ):
        self.settings = settings
        self.default_profile = default_profile
        self.default_portfolio = default_portfolio
        self.fact_extractor = OpportunityFactExtractor(settings)
        self.matcher = UserMatchAnalyzer(settings)
        self.retriever = retriever or CandidateRetriever(settings)

    async def register_user(self, session: AsyncSession, telegram_data: dict) -> TelegramUser:
        telegram_user_id = int(telegram_data["id"])
        user = await session.scalar(
            select(TelegramUser).where(TelegramUser.telegram_user_id == telegram_user_id)
        )
        if user:
            user.username = telegram_data.get("username")
            user.first_name = telegram_data.get("first_name")
            user.language_code = telegram_data.get("language_code")
            await session.commit()
            return user

        is_admin = telegram_user_id == self.settings.telegram_owner_id
        if is_admin:
            profile = self.default_profile.model_copy(deep=True)
            portfolio = [item.model_dump() for item in self.default_portfolio]
        else:
            language = telegram_data.get("language_code") or "en"
            profile = CandidateProfile(
                candidate=Candidate(
                    name=telegram_data.get("first_name") or "Candidate",
                    languages=[language],
                    skills=[],
                )
            )
            portfolio = []
        if telegram_data.get("first_name"):
            profile.candidate.name = telegram_data["first_name"]
        user = TelegramUser(
            telegram_user_id=telegram_user_id,
            username=telegram_data.get("username"),
            first_name=telegram_data.get("first_name"),
            language_code=telegram_data.get("language_code"),
            is_admin=is_admin,
            profile=profile.model_dump(),
            portfolio=portfolio,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    async def get_user(self, session: AsyncSession, telegram_user_id: int) -> TelegramUser | None:
        return await session.scalar(
            select(TelegramUser).where(TelegramUser.telegram_user_id == telegram_user_id)
        )

    async def can_register(
        self,
        session: AsyncSession,
        telegram_user_id: int,
        invite_code: str | None = None,
    ) -> bool:
        if telegram_user_id == self.settings.telegram_owner_id:
            return True
        count = await session.scalar(select(func.count()).select_from(TelegramUser)) or 0
        if count >= self.settings.max_users:
            return False
        if self.settings.registration_mode == "open":
            return True
        if self.settings.registration_mode == "closed":
            return False
        return bool(
            self.settings.registration_invite_code and invite_code == self.settings.registration_invite_code
        )

    def profile_for(self, user: TelegramUser) -> CandidateProfile:
        return CandidateProfile.model_validate(user.profile)

    def portfolio_for(self, user: TelegramUser) -> list[PortfolioProject]:
        return [PortfolioProject.model_validate(item) for item in (user.portfolio or [])]

    async def apply_profile_intake(
        self,
        session: AsyncSession,
        user: TelegramUser,
        text: str,
        *,
        minimum_budget: int | None = None,
    ) -> TelegramUser:
        """Turn one natural-language introduction into a usable search profile."""
        profile = self.profile_for(user)
        intake = await CandidateAssistant(self.settings, profile).extract_profile(text)
        profile.candidate.about = text.strip()[:6000]
        profile.candidate.skills = list(dict.fromkeys([*profile.candidate.skills, *intake.skills]))[:100]
        profile.candidate.languages = list(dict.fromkeys([*profile.candidate.languages, *intake.languages]))[
            :10
        ]
        if minimum_budget is not None:
            profile.economics.minimum_project_rub = minimum_budget
        elif intake.minimum_project_rub is not None:
            profile.economics.minimum_project_rub = intake.minimum_project_rub
        if intake.target_hourly_rub is not None:
            profile.economics.target_hourly_rub = intake.target_hourly_rub

        raw_profile = profile.model_dump()
        ui = dict((user.profile or {}).get("ui", {}))
        ui.update(
            {
                "specialties": intake.specialties,
                "onboarding_completed": True,
                "intake_state": None,
            }
        )
        raw_profile["ui"] = ui
        user.profile = raw_profile
        await session.commit()
        await self.reset_recommendations(session, user)
        await self.backfill_user(session, user)
        await session.refresh(user)
        return user

    async def ensure_match(
        self,
        session: AsyncSession,
        user: TelegramUser,
        opportunity: Opportunity,
        *,
        allow_llm_rerank: bool = True,
    ) -> UserOpportunity | None:
        if opportunity.status == OpportunityStatus.FILTERED or not is_demand_category(
            opportunity.content_category
        ):
            return None
        existing = await session.scalar(
            select(UserOpportunity).where(
                UserOpportunity.user_id == user.id,
                UserOpportunity.opportunity_id == opportunity.id,
            )
        )
        if existing:
            return existing

        profile = self.profile_for(user)
        portfolio = self.portfolio_for(user)
        facts = await self._facts_for(session, opportunity)
        eligibility = self.matcher.cheap_eligibility(user, opportunity, facts, profile)
        if not eligibility.passed:
            return None
        retrieved = await self.retriever.retrieve(
            session,
            user,
            profile,
            portfolio,
            [(opportunity, facts)],
            top_k=1,
        )
        if not retrieved or retrieved[0].score < self.settings.matching_retrieval_min_score:
            return None
        match = await self._rank_candidate(
            session,
            user,
            profile,
            portfolio,
            retrieved[0],
            eligibility.reasons,
            allow_llm_rerank=allow_llm_rerank,
        )
        if match is None:
            return None
        await session.commit()
        await session.refresh(match)
        return match

    async def backfill_user(
        self,
        session: AsyncSession,
        user: TelegramUser,
        limit: int | None = None,
        *,
        full_corpus: bool = False,
    ) -> list[tuple[UserOpportunity, Opportunity]]:
        started = perf_counter()
        query = (
            select(Opportunity)
            .where(
                Opportunity.status != OpportunityStatus.FILTERED,
                Opportunity.content_category.in_(DEMAND_CATEGORIES),
            )
            .order_by(Opportunity.published_at.desc().nullslast())
        )
        if not full_corpus:
            query = query.limit(limit if limit is not None else self.settings.onboarding_backfill_limit)
        opportunities = (await session.scalars(query)).all()
        profile = self.profile_for(user)
        portfolio = self.portfolio_for(user)
        eligible: list[tuple[Opportunity, OpportunityFacts]] = []
        eligibility_by_id: dict[str, list[str]] = {}
        rejected = 0
        for opportunity in opportunities:
            facts = await self._facts_for(session, opportunity)
            eligibility = self.matcher.cheap_eligibility(user, opportunity, facts, profile)
            if eligibility.passed:
                eligible.append((opportunity, facts))
                eligibility_by_id[str(opportunity.id)] = eligibility.reasons
            else:
                rejected += 1
        retrieved = await self.retriever.retrieve(
            session,
            user,
            profile,
            portfolio,
            eligible,
            top_k=self.settings.matching_retrieval_top_k,
        )
        matches: list[tuple[UserOpportunity, Opportunity]] = []
        persisted_count = 0
        for candidate in retrieved:
            if candidate.score < self.settings.matching_retrieval_min_score:
                continue
            existing = await session.scalar(
                select(UserOpportunity).where(
                    UserOpportunity.user_id == user.id,
                    UserOpportunity.opportunity_id == candidate.opportunity.id,
                )
            )
            if existing:
                matches.append((existing, candidate.opportunity))
                continue
            match = await self._rank_candidate(
                session,
                user,
                profile,
                portfolio,
                candidate,
                eligibility_by_id[str(candidate.opportunity.id)],
                allow_llm_rerank=False,
            )
            if match:
                matches.append((match, candidate.opportunity))
                persisted_count += 1

        rerank_count = 0
        if self.settings.matching_llm_rerank_enabled:
            ranked = sorted(matches, key=lambda pair: pair[0].final_score, reverse=True)
            for match, opportunity in ranked[: self.settings.matching_llm_rerank_top_k]:
                if match.final_score >= self.settings.matching_llm_rerank_threshold:
                    await self._rerank_existing(session, user, match, opportunity)
                    rerank_count += 1
        await session.commit()
        logger.info(
            "recommendation_batch user_id=%s scanned=%d eligibility_rejected=%d "
            "retrieval_candidates=%d ranked=%d persisted=%d rerank_count=%d latency_ms=%.2f",
            user.id,
            len(opportunities),
            rejected,
            len(retrieved),
            len(retrieved),
            persisted_count,
            rerank_count,
            (perf_counter() - started) * 1000,
        )
        return matches

    async def _rank_candidate(
        self,
        session: AsyncSession,
        user: TelegramUser,
        profile: CandidateProfile,
        portfolio: list[PortfolioProject],
        candidate: RetrievalCandidate,
        eligibility_reasons: list[str],
        *,
        allow_llm_rerank: bool,
    ) -> UserOpportunity | None:
        analysis = await self.matcher.analyze(
            candidate.opportunity,
            candidate.facts,
            profile,
            portfolio,
            retrieval_score=candidate.score,
            embedding_score=candidate.embedding_score,
            retrieval_fallback_used=candidate.fallback_used,
            allow_llm_rerank=allow_llm_rerank,
        )
        if analysis.rank_score < self.settings.matching_persist_score:
            return None
        match = UserOpportunity(
            user_id=user.id,
            opportunity_id=candidate.opportunity.id,
            eligibility_reasons=eligibility_reasons,
            status=OpportunityStatus.RECOMMENDED,
        )
        self._apply_analysis(
            match,
            candidate.opportunity,
            candidate.facts,
            analysis,
            portfolio,
        )
        session.add(match)
        await session.flush()
        return match

    async def reset_recommendations(self, session: AsyncSession, user: TelegramUser) -> None:
        await session.execute(
            delete(UserOpportunity).where(
                UserOpportunity.user_id == user.id,
                UserOpportunity.status == OpportunityStatus.RECOMMENDED,
            )
        )
        await session.commit()

    async def refresh_existing_match(
        self,
        session: AsyncSession,
        user: TelegramUser,
        match: UserOpportunity,
        opportunity: Opportunity,
        *,
        allow_llm_rerank: bool = False,
    ) -> UserOpportunity:
        """Recalculate ranking metadata without changing workflow status or proposal."""
        profile = self.profile_for(user)
        portfolio = self.portfolio_for(user)
        facts = await self._facts_for(session, opportunity)
        retrieved = await self.retriever.retrieve(
            session,
            user,
            profile,
            portfolio,
            [(opportunity, facts)],
            top_k=1,
        )
        candidate = retrieved[0]
        analysis = await self.matcher.analyze(
            opportunity,
            facts,
            profile,
            portfolio,
            retrieval_score=candidate.score,
            embedding_score=candidate.embedding_score,
            retrieval_fallback_used=candidate.fallback_used,
            allow_llm_rerank=allow_llm_rerank,
        )
        self._apply_analysis(match, opportunity, facts, analysis, portfolio)
        return match

    async def generate_proposal(
        self,
        session: AsyncSession,
        user: TelegramUser,
        match: UserOpportunity,
        opportunity: Opportunity,
    ) -> str:
        profile = self.profile_for(user)
        portfolio = next(
            (item for item in self.portfolio_for(user) if item.slug == match.portfolio_item),
            None,
        )
        proposal = await CandidateAssistant(self.settings, profile).generate_proposal(
            _to_raw(opportunity),
            match.analysis,
            portfolio,
            allow_llm=opportunity.external_ai_allowed,
        )
        match.proposal = proposal
        match.status = OpportunityStatus.APPROVED
        match.approved_at = datetime.now(UTC)
        await session.commit()
        return proposal

    async def _facts_for(
        self,
        session: AsyncSession,
        opportunity: Opportunity,
    ) -> OpportunityFacts:
        if opportunity.facts and opportunity.facts_version == FACTS_VERSION:
            return OpportunityFacts.model_validate(opportunity.facts)
        classification = ContentClassification(
            category=opportunity.content_category,
            confidence=opportunity.classification_confidence or 0.5,
            method=opportunity.classification_method or ClassificationMethod.DETERMINISTIC,
            reasons=opportunity.classification_reasons or [],
            fallback_used=opportunity.classification_fallback_used,
            fallback_failed=opportunity.classification_fallback_failed,
            latency_ms=opportunity.classification_latency_ms or 0,
            version=opportunity.classification_version or "intent-v1",
        )
        facts = await self.fact_extractor.extract(
            _to_raw(opportunity),
            classification,
            allow_llm=opportunity.external_ai_allowed,
        )
        opportunity.facts = facts.model_dump(mode="json")
        opportunity.facts_version = FACTS_VERSION
        await session.flush()
        return facts

    async def _rerank_existing(
        self,
        session: AsyncSession,
        user: TelegramUser,
        match: UserOpportunity,
        opportunity: Opportunity,
    ) -> None:
        profile = self.profile_for(user)
        portfolio = self.portfolio_for(user)
        facts = await self._facts_for(session, opportunity)
        retrieved = await self.retriever.retrieve(
            session,
            user,
            profile,
            portfolio,
            [(opportunity, facts)],
            top_k=1,
        )
        candidate = retrieved[0]
        analysis = await self.matcher.analyze(
            opportunity,
            facts,
            profile,
            portfolio,
            retrieval_score=candidate.score,
            embedding_score=candidate.embedding_score,
            retrieval_fallback_used=candidate.fallback_used,
            allow_llm_rerank=True,
        )
        self._apply_analysis(match, opportunity, facts, analysis, portfolio)

    @staticmethod
    def _apply_analysis(
        match: UserOpportunity,
        opportunity: Opportunity,
        facts: OpportunityFacts,
        analysis: UserMatchAnalysis,
        portfolio: list[PortfolioProject],
    ) -> None:
        features = analysis.feature_vector
        effort = facts.estimated_effort_max_hours or facts.estimated_effort_min_hours
        expected = facts.normalized_budget_max_rub or facts.normalized_budget_min_rub
        portfolio_item = select_portfolio(
            f"{facts.title} {' '.join(facts.skills)} {' '.join(facts.deliverables)}",
            portfolio,
        )
        match.final_score = analysis.rank_score
        match.estimated_effort_hours = effort
        match.estimated_effective_hourly_rate = None
        if expected and effort and facts.fx_status in {"normalized", "same_currency"}:
            match.estimated_effective_hourly_rate = round(expected / effort, 2)
        match.analysis = analysis.model_dump(mode="json")
        match.feature_vector = features
        match.explanation = {
            "strength_label": analysis.strength_label,
            "dimensions": {key: value.model_dump(mode="json") for key, value in analysis.dimensions.items()},
            "why_recommended": [item.model_dump(mode="json") for item in analysis.why_recommended],
            "checks": [item.model_dump(mode="json") for item in analysis.checks],
            "retrieval": {
                "method": analysis.retrieval_method,
                "score": analysis.retrieval_score,
                "fallback_used": analysis.retrieval_fallback_used,
            },
        }
        match.match_confidence = analysis.confidence
        match.reranked = analysis.reranked
        match.ranking_version = analysis.ranking_version
        match.portfolio_item = portfolio_item.slug if portfolio_item else None


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
        metadata={
            "provider_metadata": opportunity.provider_metadata,
            "external_ai_allowed": opportunity.external_ai_allowed,
        },
    )
