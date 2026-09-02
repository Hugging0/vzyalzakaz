from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AppSettings, Candidate, CandidateProfile, PortfolioProject
from app.models import Opportunity, OpportunityStatus, TelegramUser, UserOpportunity
from app.schemas import RawOpportunity
from app.services.portfolio import select_portfolio
from app.services.prefilter import evaluate
from app.services.ranking import freshness_score
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
            self.settings.registration_invite_code
            and invite_code == self.settings.registration_invite_code
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
        intake = await OpportunityAnalyzer(self.settings, profile).extract_profile(text)
        profile.candidate.about = text.strip()[:6000]
        profile.candidate.skills = list(dict.fromkeys([*profile.candidate.skills, *intake.skills]))[:100]
        profile.candidate.languages = list(
            dict.fromkeys([*profile.candidate.languages, *intake.languages])
        )[:10]
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
        if not source_matches_specialties(user, opportunity):
            return None
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
        if not personalized.required_skills:
            return None
        analysis = dict(opportunity.analysis or {})
        analysis.update(
            {
                "required_skills": personalized.required_skills,
                "missing_skills": personalized.missing_skills,
                "fit_reason": personalized.fit_reason,
                "recommended_portfolio_project": portfolio_item.slug if portfolio_item else "",
            }
        )
        money = personalized.money_score
        effort = opportunity.estimated_effort_hours or personalized.estimated_hours or None
        fresh = freshness_score(opportunity.published_at)
        score = personalized_match_score(
            personalized.fit_score,
            prefilter.score,
            money,
            personalized.win_score,
            fresh,
        )
        if score < min(profile.ranking.digest_threshold, 60):
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


def personalized_match_score(
    fit: float,
    prefilter: float,
    money: float,
    win: float,
    freshness: float,
) -> float:
    """Calibrated match score shown as a percentage in the personal product UI."""
    score = fit * 0.55 + prefilter * 0.20 + money * 0.10 + win * 0.10 + freshness * 0.05
    return round(max(0.0, min(100.0, score)), 2)


def source_matches_specialties(user: TelegramUser, opportunity: Opportunity) -> bool:
    ui = (user.profile or {}).get("ui", {})
    preferred_sources = set(ui.get("preferred_sources", []))
    if preferred_sources and opportunity.source not in preferred_sources:
        return False
    excluded_keywords = {
        value.casefold().strip() for value in ui.get("excluded_keywords", []) if value.strip()
    }
    searchable = f"{opportunity.title} {opportunity.description}".casefold()
    if any(keyword in searchable for keyword in excluded_keywords):
        return False
    project_types = {
        value.casefold().strip() for value in ui.get("project_types", []) if value.strip()
    }
    employment_type = (opportunity.employment_type or "").casefold()
    if project_types and employment_type:
        if not any(value in employment_type or employment_type in value for value in project_types):
            return False
    specialties = set(ui.get("specialties", []))
    if not specialties:
        profile = CandidateProfile.model_validate(user.profile)
        skills = " ".join(profile.candidate.skills).casefold()
        inferred = {
            "Разработка": ("python", "fastapi", "django", "react", "javascript", "typescript"),
            "Дизайн": ("figma", "ui/ux", "web design", "branding"),
            "Маркетинг": ("smm", "seo", "marketing"),
            "Тексты": ("copywriting", "content", "editor"),
            "Видео": ("video", "motion"),
        }
        specialties = {
            name for name, markers in inferred.items() if any(marker in skills for marker in markers)
        }
    if not specialties:
        return True
    source = opportunity.source.casefold()
    if "marketing" in source:
        return "Маркетинг" in specialties
    if "copywriting" in source:
        return "Тексты" in specialties
    if "design" in source:
        return bool({"Дизайн", "Видео"} & specialties)
    return True


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
