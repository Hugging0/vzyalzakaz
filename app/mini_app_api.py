from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import AliasChoices, BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AppSettings, CandidateProfile, PortfolioProject
from app.database import get_session
from app.mini_app_auth import create_session_token, current_mini_app_user, validate_init_data
from app.models import (
    ApplicationEvent,
    CollectorRun,
    Opportunity,
    OpportunityStatus,
    Payment,
    TelegramUser,
    UserOpportunity,
)
from app.services.application_workflow import record_event, transition_application
from app.services.payments import YooKassaService, payment_payload
from app.services.web_sessions import (
    clear_session_cookie,
    create_web_session,
    exchange_login_ticket,
    revoke_web_session,
    set_session_cookie,
)

router = APIRouter(prefix="/api")
CurrentUser = Annotated[TelegramUser, Depends(current_mini_app_user)]
DEFAULT_NOTIFICATIONS = {
    "strongMatches": True,
    "replies": True,
    "connectionIssues": True,
}


class TelegramAuthRequest(BaseModel):
    init_data: str = Field(min_length=1, max_length=12_000)


class ProfileUpdate(BaseModel):
    skills: list[str] | None = Field(default=None, max_length=100)
    languages: list[str] | None = Field(default=None, max_length=10)
    about: str | None = Field(default=None, max_length=6_000)
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
    excluded_keywords: list[str] | None = Field(
        default=None,
        validation_alias=AliasChoices("excluded_keywords", "excludedKeywords"),
        max_length=50,
    )
    preferred_sources: list[str] | None = Field(
        default=None,
        validation_alias=AliasChoices("preferred_sources", "preferredSources"),
        max_length=100,
    )
    automation_level: str | None = Field(
        default=None,
        validation_alias=AliasChoices("automation_level", "automationLevel"),
        pattern="^(manual|drafts)$",
    )
    notifications: dict[str, bool] | None = None


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


class PortfolioUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=1_500)
    skills: list[str] | None = Field(default=None, max_length=50)
    url: str | None = Field(default=None, max_length=2_000)


class WebTicketExchange(BaseModel):
    ticket: str = Field(min_length=24, max_length=255)


class LeadStatusUpdate(BaseModel):
    status: OpportunityStatus
    detail: str | None = Field(default=None, max_length=255)


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
        "excludedKeywords": ui.get("excluded_keywords", []),
        "preferredSources": ui.get("preferred_sources", []),
        "automationLevel": ui.get("automation_level", "drafts"),
        "notifications": {**DEFAULT_NOTIFICATIONS, **ui.get("notifications", {})},
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
        "created_at": match.created_at.isoformat(),
        "contacted_at": match.contacted_at.isoformat() if match.contacted_at else None,
        "apply_mode": opportunity.apply_mode,
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


@router.post("/web/auth/bootstrap")
async def bootstrap_web_session(
    response: Response,
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict:
    settings: AppSettings = request.app.state.runtime.settings
    token = await create_web_session(session, user, settings)
    set_session_cookie(response, token, settings)
    return {"authenticated": True}


@router.post("/web/auth/exchange")
async def exchange_web_ticket(
    payload: WebTicketExchange,
    response: Response,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    settings: AppSettings = request.app.state.runtime.settings
    user, token = await exchange_login_ticket(session, payload.ticket, settings)
    set_session_cookie(response, token, settings)
    return {"authenticated": True, "firstName": user.first_name}


@router.post("/web/auth/logout")
async def logout_web_session(
    response: Response,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    settings: AppSettings = request.app.state.runtime.settings
    await revoke_web_session(session, request.cookies.get(settings.web_session_cookie_name))
    clear_session_cookie(response, settings)
    return {"authenticated": False}


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
    if payload.excluded_keywords is not None:
        ui["excluded_keywords"] = _clean_values(payload.excluded_keywords, 50)
    if payload.preferred_sources is not None:
        ui["preferred_sources"] = _clean_values(payload.preferred_sources, 100)
    if payload.automation_level is not None:
        ui["automation_level"] = payload.automation_level
    if payload.notifications is not None:
        notifications = {**DEFAULT_NOTIFICATIONS, **ui.get("notifications", {})}
        notifications.update(
            {
                key: bool(value)
                for key, value in payload.notifications.items()
                if key in DEFAULT_NOTIFICATIONS
            }
        )
        ui["notifications"] = notifications
    if payload.onboarding_completed is not None:
        ui["onboarding_completed"] = payload.onboarding_completed
    raw_profile["ui"] = ui
    db_user.profile = raw_profile
    ranking_fields = {
        "skills",
        "languages",
        "about",
        "minimum_budget",
        "hourly_rate",
        "specialties",
        "project_types",
        "excluded_keywords",
        "preferred_sources",
    }
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
    status: OpportunityStatus | None = None,
    minimum_score: float = Query(default=0, ge=0, le=100),
    source: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[dict]:
    query = (
        select(UserOpportunity, Opportunity)
        .join(Opportunity, Opportunity.id == UserOpportunity.opportunity_id)
        .where(
            UserOpportunity.user_id == user.id,
            UserOpportunity.final_score >= minimum_score,
        )
    )
    if status is not None:
        query = query.where(UserOpportunity.status == status)
    if source:
        query = query.where(Opportunity.source == source)
    rows = (
        await session.execute(
            query.order_by(
                UserOpportunity.final_score.desc(),
                Opportunity.published_at.desc().nullslast(),
            )
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return [_lead_payload(match, opportunity) for match, opportunity in rows]


@router.get("/app/leads/{match_id}")
async def read_lead(
    match_id: int,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict:
    match, opportunity = await _owned_match(session, user, match_id)
    return _lead_payload(match, opportunity)


@router.get("/app/leads/{match_id}/events")
async def list_lead_events(
    match_id: int,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    match, _ = await _owned_match(session, user, match_id)
    events = (
        await session.scalars(
            select(ApplicationEvent)
            .where(
                ApplicationEvent.user_opportunity_id == match.id,
                ApplicationEvent.user_id == user.id,
            )
            .order_by(ApplicationEvent.created_at.asc())
        )
    ).all()
    return [
        {
            "id": event.id,
            "event": event.event,
            "detail": event.detail,
            "actor": event.actor,
            "createdAt": event.created_at.isoformat(),
        }
        for event in events
    ]


@router.post("/app/leads/{match_id}/skip")
async def skip_lead(match_id: int, user: CurrentUser, session: AsyncSession = Depends(get_session)) -> dict:
    match, _ = await _owned_match(session, user, match_id)
    await transition_application(
        session,
        match,
        OpportunityStatus.SKIPPED,
        actor="web",
    )
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
    await record_event(session, match, "proposal_ready", actor="web")
    await session.commit()
    return {"proposal": proposal}


@router.patch("/app/leads/{match_id}/proposal")
async def update_proposal(
    match_id: int, payload: ProposalUpdate, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> dict:
    match, _ = await _owned_match(session, user, match_id)
    if match.status in {OpportunityStatus.CONTACTED, OpportunityStatus.WON, OpportunityStatus.LOST}:
        raise HTTPException(409, "Proposal can no longer be changed for this lead")
    match.proposal = payload.proposal.strip()
    if match.status == OpportunityStatus.RECOMMENDED:
        await transition_application(
            session,
            match,
            OpportunityStatus.APPROVED,
            actor="web",
            detail="Текст отклика сохранён",
        )
    else:
        await record_event(session, match, "proposal_updated", actor="web")
        await session.commit()
    return {"proposal": match.proposal}


@router.post("/app/leads/{match_id}/contacted")
async def mark_contacted(
    match_id: int, user: CurrentUser, session: AsyncSession = Depends(get_session)
) -> dict:
    match, _ = await _owned_match(session, user, match_id)
    await transition_application(
        session,
        match,
        OpportunityStatus.CONTACTED,
        actor="web",
    )
    return {"status": match.status.value}


@router.patch("/app/leads/{match_id}/status")
async def update_lead_status(
    match_id: int,
    payload: LeadStatusUpdate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict:
    match, _ = await _owned_match(session, user, match_id)
    await transition_application(
        session,
        match,
        payload.status,
        actor="web",
        detail=payload.detail,
    )
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
    scanned = await session.scalar(select(func.count()).select_from(Opportunity)) or 0
    sent_statuses = {
        OpportunityStatus.CONTACTED,
        OpportunityStatus.REPLIED,
        OpportunityStatus.INTERVIEW,
        OpportunityStatus.WON,
        OpportunityStatus.LOST,
    }
    response_statuses = {
        OpportunityStatus.REPLIED,
        OpportunityStatus.INTERVIEW,
        OpportunityStatus.WON,
    }
    sent = sum(counts.get(status, 0) for status in sent_statuses)
    responses = sum(counts.get(status, 0) for status in response_statuses)
    approved = counts.get(OpportunityStatus.APPROVED, 0) + sent
    interviews = counts.get(OpportunityStatus.INTERVIEW, 0) + counts.get(
        OpportunityStatus.WON, 0
    )
    proposals = (
        await session.scalar(
            select(func.count())
            .select_from(UserOpportunity)
            .where(
                UserOpportunity.user_id == user.id,
                UserOpportunity.proposal.is_not(None),
            )
        )
        or 0
    )
    source_rows = (
        await session.execute(
            select(Opportunity.source, func.count())
            .join(UserOpportunity, UserOpportunity.opportunity_id == Opportunity.id)
            .where(UserOpportunity.user_id == user.id)
            .group_by(Opportunity.source)
            .order_by(func.count().desc())
            .limit(5)
        )
    ).all()
    return {
        "scanned": scanned,
        "relevant": sum(counts.values()),
        "approved": approved,
        "sent": sent,
        "replied": responses,
        "interviews": interviews,
        "won": counts.get(OpportunityStatus.WON, 0),
        "lost": counts.get(OpportunityStatus.LOST, 0),
        "pendingActions": counts.get(OpportunityStatus.RECOMMENDED, 0)
        + counts.get(OpportunityStatus.APPROVED, 0),
        "responseRate": round((responses / sent) * 100, 1) if sent else 0,
        "estimatedTimeSavedMinutes": proposals * 10,
        "topSources": [{"source": source, "count": count} for source, count in source_rows],
    }


@router.get("/app/sources")
async def list_sources(
    request: Request,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    del user
    configured = request.app.state.runtime.settings.load_sources()
    latest_ids = (
        select(CollectorRun.source, func.max(CollectorRun.id).label("run_id"))
        .group_by(CollectorRun.source)
        .subquery()
    )
    runs = (
        await session.scalars(
            select(CollectorRun).join(latest_ids, CollectorRun.id == latest_ids.c.run_id)
        )
    ).all()
    latest = {run.source: run for run in runs}
    result = []
    for source in configured:
        run = latest.get(source.name)
        if not source.enabled:
            connection_status = "planned" if source.collector == "pending" else "available"
        elif run and run.error:
            connection_status = "attention"
        elif run:
            connection_status = "connected"
        else:
            connection_status = "syncing"
        capabilities = list(dict.fromkeys(source.capabilities))
        if source.apply_mode in {"send_allowed", "api_allowed"} and "quick_apply" not in capabilities:
            capabilities.append("quick_apply")
        if source.submission_type == "browser_extension" and "autofill" not in capabilities:
            capabilities.append("autofill")
        result.append(
            {
                "name": source.name,
                "displayName": source.display_name or _source_display_name(source.name),
                "sourceType": source.type,
                "enabled": source.enabled,
                "connectionStatus": connection_status,
                "submissionType": source.submission_type,
                "capabilities": capabilities,
                "lastRunAt": run.finished_at.isoformat() if run and run.finished_at else None,
                "lastError": run.error[:240] if run and run.error else None,
            }
        )
    return result


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


@router.patch("/app/portfolio/{slug}")
async def update_portfolio(
    slug: str,
    payload: PortfolioUpdate,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict:
    db_user = await session.get(TelegramUser, user.id)
    projects = _portfolio_for(db_user)
    project = next((item for item in projects if item.slug == slug), None)
    if not project:
        raise HTTPException(404, "Кейс не найден")
    values = payload.model_dump(exclude_unset=True)
    if "title" in values:
        project.title = values["title"].strip()
    if "description" in values:
        project.description = values["description"].strip()
    if "skills" in values:
        project.skills = _clean_values(values["skills"], 50)
    if "url" in values:
        project.url = values["url"].strip() if values["url"] else None
    db_user.portfolio = [item.model_dump() for item in projects]
    await session.commit()
    return project.model_dump()


@router.delete("/app/portfolio/{slug}")
async def delete_portfolio(
    slug: str,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
) -> dict:
    db_user = await session.get(TelegramUser, user.id)
    projects = _portfolio_for(db_user)
    remaining = [item for item in projects if item.slug != slug]
    if len(remaining) == len(projects):
        raise HTTPException(404, "Кейс не найден")
    db_user.portfolio = [item.model_dump() for item in remaining]
    await session.commit()
    return {"deleted": True}


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


def _source_display_name(name: str) -> str:
    known = {
        "hh_ru": "HeadHunter",
        "freelancer_com": "Freelancer",
        "fl_ru": "FL.ru",
        "freelance_ru": "Freelance.ru",
        "kwork_projects": "Kwork",
        "hackernews": "Hacker News",
        "remoteok": "Remote OK",
        "weworkremotely": "We Work Remotely",
    }
    return known.get(name, name.removeprefix("telegram_").replace("_", " ").title())
