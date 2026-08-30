from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AppSettings, Candidate, CandidateProfile, PortfolioProject
from app.models import Opportunity, OpportunityStatus, TelegramUser, UserOpportunity
from app.schemas import RawOpportunity
from app.services.portfolio import select_portfolio
from app.services.prefilter import evaluate
from app.services.ranking import final_score, freshness_score
from app.services.scoring import OpportunityAnalyzer


class RecommendationService:
    """Creates isolated, personalized matches without repeating the global LLM call."""

    def __init__(
        self,
        settings: AppSettings,
        default_profile: CandidateProfile,
        default_portfolio: list[PortfolioProject],
    ):
        self.settings = settings
        self.default_profile = default_profile
        self.default_portfolio = default_portfolio

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

    def profile_for(self, user: TelegramUser) -> CandidateProfile:
        return CandidateProfile.model_validate(user.profile)

    def portfolio_for(self, user: TelegramUser) -> list[PortfolioProject]:
        return [PortfolioProject.model_validate(item) for item in (user.portfolio or [])]

    async def ensure_match(
        self,
        session: AsyncSession,
        user: TelegramUser,
        opportunity: Opportunity,
    ) -> UserOpportunity | None:
        existing = await session.scalar(
            select(UserOpportunity).where(
                UserOpportunity.user_id == user.id,
                UserOpportunity.opportunity_id == opportunity.id,
            )
        )
        if existing:
            return existing

        profile = self.profile_for(user)
        raw = _to_raw(opportunity)
        prefilter = evaluate(raw, profile)
        if not prefilter.passed:
            return None

        portfolio = self.portfolio_for(user)
        portfolio_item = select_portfolio(
            f"{opportunity.title} {opportunity.description} {opportunity.raw_text}", portfolio
        )
        local_settings = self.settings.model_copy(update={"llm_provider": "disabled", "llm_api_key": None})
        personalized = await OpportunityAnalyzer(local_settings, profile).analyze(raw, portfolio_item)
        analysis = dict(opportunity.analysis or {})
        analysis.update(
            {
                "required_skills": personalized.required_skills,
                "missing_skills": personalized.missing_skills,
                "fit_reason": personalized.fit_reason,
                "recommended_portfolio_project": portfolio_item.slug if portfolio_item else "",
            }
        )
        money = opportunity.money_score if opportunity.money_score is not None else personalized.money_score
        effort = opportunity.estimated_effort_hours or personalized.estimated_hours or None
        fresh = freshness_score(opportunity.published_at)
        score = final_score(
            personalized.fit_score,
            money,
            personalized.win_score,
            fresh,
            profile.ranking,
        )
        if score < profile.ranking.digest_threshold:
            return None

        effective_rate = None
        expected = opportunity.budget_max or opportunity.budget_min
        if expected and effort and opportunity.currency == "RUB":
            effective_rate = round(expected / effort, 2)
        match = UserOpportunity(
            user_id=user.id,
            opportunity_id=opportunity.id,
            prefilter_score=prefilter.score,
            prefilter_reasons=prefilter.reasons,
            fit_score=personalized.fit_score,
            money_score=money,
            win_score=personalized.win_score,
            freshness_score=fresh,
            final_score=score,
            estimated_effort_hours=effort,
            estimated_effective_hourly_rate=effective_rate,
            analysis=analysis,
            portfolio_item=portfolio_item.slug if portfolio_item else None,
            status=OpportunityStatus.RECOMMENDED,
        )
        session.add(match)
        await session.commit()
        await session.refresh(match)
        return match

    async def backfill_user(
        self, session: AsyncSession, user: TelegramUser, limit: int | None = None
    ) -> list[tuple[UserOpportunity, Opportunity]]:
        opportunities = (
            await session.scalars(
                select(Opportunity)
                .where(Opportunity.status != OpportunityStatus.FILTERED)
                .order_by(Opportunity.published_at.desc().nullslast())
                .limit(limit or self.settings.onboarding_backfill_limit)
            )
        ).all()
        matches = []
        for opportunity in opportunities:
            match = await self.ensure_match(session, user, opportunity)
            if match:
                matches.append((match, opportunity))
        return matches

    async def reset_recommendations(self, session: AsyncSession, user: TelegramUser) -> None:
        await session.execute(
            delete(UserOpportunity).where(
                UserOpportunity.user_id == user.id,
                UserOpportunity.status == OpportunityStatus.RECOMMENDED,
            )
        )
        await session.commit()

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
        proposal = await OpportunityAnalyzer(self.settings, profile).generate_proposal(
            _to_raw(opportunity), match.analysis, portfolio
        )
        match.proposal = proposal
        match.status = OpportunityStatus.APPROVED
        match.approved_at = datetime.now(UTC)
        await session.commit()
        return proposal


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
