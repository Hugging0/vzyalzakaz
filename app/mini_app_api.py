from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import AliasChoices, BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AppSettings, CandidateProfile, PortfolioProject
from app.database import get_session
from app.mini_app_auth import create_session_token, current_mini_app_user, validate_init_data
from app.models import Opportunity, OpportunityStatus, Payment, TelegramUser, UserOpportunity
from app.services.payments import YooKassaService, payment_payload

router = APIRouter(prefix="/api")
CurrentUser = Annotated[TelegramUser, Depends(current_mini_app_user)]


class TelegramAuthRequest(BaseModel):
    init_data: str = Field(min_length=1, max_length=12_000)


class ProfileUpdate(BaseModel):
    skills: list[str] | None = Field(default=None, max_length=100)
    languages: list[str] | None = Field(default=None, max_length=10)
    about: str | None = Field(default=None, max_length=2_000)
    minimum_budget: int | None = Field(
        default=None, validation_alias=AliasChoices("minimum_budget", "minimumBudget"), ge=0, le=100_000_000
    )
    hourly_rate: int | None = Field(
        default=None, validation_alias=AliasChoices("hourly_rate", "hourlyRate"), ge=0, le=1_000_000
    )
    match_threshold: float | None = Field(
        default=None,
        validation_alias=AliasChoices("match_threshold", "matchThreshold"),
        ge=60,
        le=95,
    )
    specialties: list[str] | None = Field(default=None, max_length=20)
    project_types: list[str] | None = Field(default=None, max_length=20)
    onboarding_completed: bool | None = Field(
        default=None, validation_alias=AliasChoices("onboarding_completed", "onboardingCompleted")
    )


class OnboardingCreate(BaseModel):
    about: str = Field(min_length=20, max_length=6_000)
    minimum_budget: int | None = Field(
        default=None,
        validation_alias=AliasChoices("minimum_budget", "minimumBudget"),
        ge=0,
        le=100_000_000,
    )


class ProposalUpdate(BaseModel):
    proposal: str = Field(min_length=1, max_length=10_000)


class AgentUpdate(BaseModel):
    is_active: bool


class PortfolioCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1_500)
    skills: list[str] = Field(default_factory=list, max_length=50)
    url: str | None = Field(default=None, max_length=2_000)


class YooKassaWebhook(BaseModel):
    event: str
    object: dict


def _profile_payload(user: TelegramUser) -> dict:
    profile = CandidateProfile.model_validate(user.profile)
    ui = (user.profile or {}).get("ui", {})
    return {
        "firstName": user.first_name,
        "isActive": user.is_active,
        "skills": profile.candidate.skills,
        "languages": profile.candidate.languages,
        "about": profile.candidate.about,
        "minimumBudget": profile.economics.minimum_project_rub,
        "hourlyRate": profile.economics.target_hourly_rub,
        "matchThreshold": profile.ranking.realtime_threshold,
        "specialties": ui.get("specialties", []),
        "projectTypes": ui.get("project_types", []),
        "onboardingCompleted": bool(ui.get("onboarding_completed", bool(profile.candidate.skills))),
    }


def _lead_payload(match: UserOpportunity, opportunity: Opportunity) -> dict:
    if opportunity.budget_min or opportunity.budget_max:
        low = f"{opportunity.budget_min:,.0f}" if opportunity.budget_min else "?"
        high = f"{opportunity.budget_max:,.0f}" if opportunity.budget_max else "?"
        budget = f"{low}–{high} {opportunity.currency or ''}".strip()
    else:
        budget = "Бюджет не указан"
    return {
        "id": match.id,
        "opportunity_id": str(opportunity.id),
        "title": opportunity.title,
        "description": opportunity.description,
        "source": opportunity.source,
        "source_url": opportunity.source_url,
        "budget_label": budget,
        "final_score": match.final_score,
        "analysis": match.analysis or {},
        "portfolio_item": match.portfolio_item,
        "proposal": match.proposal,
        "status": match.status.value,
        "published_at": opportunity.published_at.isoformat() if opportunity.published_at else None,
    }


async def _owned_match(
    session: AsyncSession, user: TelegramUser, match_id: int
) -> tuple[UserOpportunity, Opportunity]:
    row = (
        await session.execute(
            select(UserOpportunity, Opportunity)
            .join(Opportunity, Opportunity.id == UserOpportunity.opportunity_id)
            .where(UserOpportunity.id == match_id, UserOpportunity.user_id == user.id)
        )
    ).one_or_none()
    if not row:
        raise HTTPException(404, "Lead not found")
    return row


@router.post("/mini-app/auth")
async def mini_app_auth(payload: TelegramAuthRequest, request: Request) -> dict:
    settings = request.app.state.runtime.settings
    telegram_data = validate_init_data(payload.init_data, settings)
    async with request.app.state.runtime.session_factory() as session:
        user = await session.scalar(
            select(TelegramUser).where(TelegramUser.telegram_user_id == int(telegram_data["id"]))
        )
        if not user:
            allowed = await request.app.state.runtime.recommendations.can_register(
                session, int(telegram_data["id"])
            )
            if not allowed:
                raise HTTPException(
                    403,
                    "Регистрация по приглашениям. Сначала активируйте приглашение в боте.",
                )
            user = await request.app.state.runtime.recommendations.register_user(
                session, telegram_data
            )
    return {"token": create_session_token(user.telegram_user_id, settings)}


@router.post("/mini-app/auth/dev")
async def mini_app_dev_auth(request: Request) -> dict:
    settings: AppSettings = request.app.state.runtime.settings
    if not settings.allow_dev_auth or not settings.dev_telegram_user_id:
        raise HTTPException(404, "Not found")
    async with request.app.state.runtime.session_factory() as session:
        user = await request.app.state.runtime.recommendations.register_user(
            session, {"id": settings.dev_telegram_user_id, "first_name": "Developer", "language_code": "ru"}
        )
    return {"token": create_session_token(user.telegram_user_id, settings)}


@router.get("/app/me")
async def read_profile(user: CurrentUser) -> dict:
    return _profile_payload(user)


@router.patch("/app/me")
async def update_profile(
    payload: ProfileUpdate,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict:
    db_user = await session.get(TelegramUser, user.id)
    profile = CandidateProfile.model_validate(db_user.profile)
    if payload.skills is not None:
        profile.candidate.skills = _clean_values(payload.skills, 100)
    if payload.languages is not None:
        profile.candidate.languages = _clean_values(payload.languages, 10)
    if payload.about is not None:
        profile.candidate.about = payload.about.strip()
    if payload.minimum_budget is not None:
        profile.economics.minimum_project_rub = payload.minimum_budget
    if payload.hourly_rate is not None:
        profile.economics.target_hourly_rub = payload.hourly_rate
    if payload.match_threshold is not None:
        profile.ranking.realtime_threshold = payload.match_threshold
    raw_profile = profile.model_dump()
    ui = dict((db_user.profile or {}).get("ui", {}))
    if payload.specialties is not None:
        ui["specialties"] = _clean_values(payload.specialties, 20)
    if payload.project_types is not None:
        ui["project_types"] = _clean_values(payload.project_types, 20)
    if payload.onboarding_completed is not None:
        ui["onboarding_completed"] = payload.onboarding_completed
    raw_profile["ui"] = ui
    db_user.profile = raw_profile
    ranking_fields = {"skills", "languages", "about", "minimum_budget", "hourly_rate"}
    should_rescore = bool(payload.model_fields_set & ranking_fields)
    if should_rescore:
        await request.app.state.runtime.recommendations.reset_recommendations(session, db_user)
        await request.app.state.runtime.recommendations.backfill_user(session, db_user)
    else:
        await session.commit()
    await session.refresh(db_user)
    return _profile_payload(db_user)


@router.post("/app/onboarding")
async def complete_onboarding(
    payload: OnboardingCreate,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict:
    db_user = await session.get(TelegramUser, user.id)
    await request.app.state.runtime.recommendations.apply_profile_intake(
        session,
        db_user,
        payload.about,
        minimum_budget=payload.minimum_budget,
    )
    return _profile_payload(db_user)


@router.get("/app/leads")
async def list_leads(
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    rows = (
        await session.execute(
            select(UserOpportunity, Opportunity)
            .join(Opportunity, Opportunity.id == UserOpportunity.opportunity_id)
            .where(UserOpportunity.user_id == user.id)
            .order_by(UserOpportunity.final_score.desc(), Opportunity.published_at.desc().nullslast())
            .limit(100)
        )
    ).all()
    return [_lead_payload(match, opportunity) for match, opportunity in rows]


@router.post("/app/leads/{match_id}/skip")
async def skip_lead(match_id: int, user: CurrentUser, session: AsyncSession = Depends(get_session)) -> dict:
    match, _ = await _owned_match(session, user, match_id)
    if match.status not in {OpportunityStatus.CONTACTED, OpportunityStatus.WON, OpportunityStatus.LOST}:
        match.status = OpportunityStatus.SKIPPED
        await session.commit()
    return {"status": match.status.value}


@router.post("/app/leads/{match_id}/proposal")
async def prepare_proposal(
    match_id: int, request: Request, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> dict:
    match, opportunity = await _owned_match(session, user, match_id)
    if match.status in {OpportunityStatus.CONTACTED, OpportunityStatus.WON, OpportunityStatus.LOST}:
        raise HTTPException(409, "Proposal can no longer be changed for this lead")
    proposal = await request.app.state.runtime.recommendations.generate_proposal(
        session, user, match, opportunity
    )
    return {"proposal": proposal}


@router.patch("/app/leads/{match_id}/proposal")
async def update_proposal(
    match_id: int, payload: ProposalUpdate, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> dict:
    match, _ = await _owned_match(session, user, match_id)
    if match.status in {OpportunityStatus.CONTACTED, OpportunityStatus.WON, OpportunityStatus.LOST}:
        raise HTTPException(409, "Proposal can no longer be changed for this lead")
    match.proposal = payload.proposal.strip()
    match.status = OpportunityStatus.APPROVED
    await session.commit()
    return {"proposal": match.proposal}


@router.post("/app/leads/{match_id}/contacted")
async def mark_contacted(
    match_id: int, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> dict:
    match, _ = await _owned_match(session, user, match_id)
    if match.status == OpportunityStatus.CONTACTED:
        return {"status": match.status.value}
    if match.status != OpportunityStatus.APPROVED or not match.proposal:
        raise HTTPException(409, "Prepare and review the proposal before marking it as sent")
    match.status = OpportunityStatus.CONTACTED
    match.contacted_at = datetime.now(UTC)
    await session.commit()
    return {"status": match.status.value}


@router.get("/app/analytics")
async def personal_analytics(user: CurrentUser, session: AsyncSession = Depends(get_session)) -> dict:
    rows = (
        await session.execute(
            select(UserOpportunity.status, func.count())
            .where(UserOpportunity.user_id == user.id)
            .group_by(UserOpportunity.status)
        )
    ).all()
    counts = {status: count for status, count in rows}
    return {
        "relevant": sum(counts.values()),
        "approved": counts.get(OpportunityStatus.APPROVED, 0),
        "sent": counts.get(OpportunityStatus.CONTACTED, 0),
        "replied": counts.get(OpportunityStatus.REPLIED, 0),
        "won": counts.get(OpportunityStatus.WON, 0),
    }


@router.get("/app/portfolio")
async def list_portfolio(user: CurrentUser) -> list[dict]:
    return [item.model_dump() for item in _portfolio_for(user)]


@router.post("/app/portfolio")
async def add_portfolio(
    payload: PortfolioCreate, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> dict:
    db_user = await session.get(TelegramUser, user.id)
    slug = re.sub(r"[^a-z0-9]+", "-", payload.title.lower()).strip("-") or "case"
    project = PortfolioProject(
        slug=f"{slug}-{int(datetime.now(UTC).timestamp())}",
        title=payload.title.strip(),
        description=payload.description.strip(),
        skills=_clean_values(payload.skills, 50),
        url=payload.url.strip() if payload.url else None,
    )
    db_user.portfolio = [*(db_user.portfolio or []), project.model_dump()]
    await session.commit()
    return project.model_dump()


@router.patch("/app/agent")
async def set_agent_active(
    payload: AgentUpdate, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> dict:
    db_user = await session.get(TelegramUser, user.id)
    db_user.is_active = payload.is_active
    await session.commit()
    await session.refresh(db_user)
    return _profile_payload(db_user)


@router.get("/app/billing")
async def billing_status(
    request: Request, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> dict:
    payment = await session.scalar(
        select(Payment)
        .where(Payment.user_id == user.id)
        .order_by(Payment.created_at.desc())
        .limit(1)
    )
    payload = payment_payload(payment)
    payload["checkout_available"] = request.app.state.runtime.settings.yookassa_ready
    return payload


@router.post("/app/billing/checkout")
async def create_checkout(
    request: Request,
    user: CurrentUser,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=16, max_length=255),
    session: AsyncSession = Depends(get_session),
) -> dict:
    payment = await YooKassaService(request.app.state.runtime.settings).create_payment(
        session, user, idempotency_key
    )
    return payment_payload(payment)


@router.post("/app/billing/refresh")
async def refresh_billing(
    request: Request, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> dict:
    payment = await session.scalar(
        select(Payment)
        .where(Payment.user_id == user.id)
        .order_by(Payment.created_at.desc())
        .limit(1)
    )
    if not payment:
        return payment_payload(None)
    refreshed = await YooKassaService(request.app.state.runtime.settings).refresh_payment(session, payment)
    return payment_payload(refreshed)


@router.post("/webhooks/yookassa", status_code=200)
async def yookassa_webhook(
    payload: YooKassaWebhook,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    provider_payment_id = payload.object.get("id")
    if not isinstance(provider_payment_id, str):
        raise HTTPException(400, "YooKassa payment id is missing")
    payment = await session.scalar(
        select(Payment).where(Payment.provider_payment_id == provider_payment_id)
    )
    if payment:
        await YooKassaService(request.app.state.runtime.settings).refresh_payment(session, payment)
    return {"ok": True}


def _clean_values(values: list[str], maximum: int) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))[:maximum]


def _portfolio_for(user: TelegramUser) -> list[PortfolioProject]:
    return [PortfolioProject.model_validate(item) for item in (user.portfolio or [])]
