from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Opportunity, OpportunityStatus, TelegramUser, UserOpportunity
from app.schemas import AnalyticsRead, OpportunityRead, StatusUpdate

router = APIRouter(prefix="/api")


@router.get("/health")
async def health(request: Request) -> dict:
    runtime = request.app.state.runtime
    return {
        "status": "ok",
        "llm_provider": runtime.settings.llm_provider,
        "scheduler": bool(runtime.scheduler and runtime.scheduler.running),
        "telegram_collector": bool(runtime.telegram_collector),
        "telegram_bot": bool(runtime.telegram_bot),
    }


@router.get("/opportunities", response_model=list[OpportunityRead])
async def opportunities(
    status: OpportunityStatus | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[Opportunity]:
    query = select(Opportunity)
    if status:
        query = query.where(Opportunity.status == status)
    query = query.order_by(Opportunity.collected_at.desc())
    return list((await session.scalars(query.offset(offset).limit(limit))).all())


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityRead)
async def opportunity(opportunity_id: UUID, session: AsyncSession = Depends(get_session)) -> Opportunity:
    item = await session.get(Opportunity, opportunity_id)
    if not item:
        raise HTTPException(404, "Opportunity not found")
    return item


@router.patch("/opportunities/{opportunity_id}/status", response_model=OpportunityRead)
async def update_status(
    opportunity_id: UUID,
    update: StatusUpdate,
    session: AsyncSession = Depends(get_session),
) -> Opportunity:
    item = await session.get(Opportunity, opportunity_id)
    if not item:
        raise HTTPException(404, "Opportunity not found")
    if update.status not in {OpportunityStatus.NEW, OpportunityStatus.FILTERED}:
        raise HTTPException(422, "Global opportunity status can only be new or filtered")
    item.status = update.status
    item.skip_reason = update.reason if update.status == OpportunityStatus.FILTERED else None
    await session.commit()
    await session.refresh(item)
    return item


@router.get("/analytics", response_model=AnalyticsRead)
async def analytics(session: AsyncSession = Depends(get_session)) -> AnalyticsRead:
    global_rows = (
        await session.execute(select(Opportunity.status, func.count()).group_by(Opportunity.status))
    ).all()
    global_counts = {status: count for status, count in global_rows}
    personal_rows = (
        await session.execute(
            select(UserOpportunity.status, func.count()).group_by(UserOpportunity.status)
        )
    ).all()
    personal_counts = {status: count for status, count in personal_rows}
    total = await session.scalar(select(func.count()).select_from(Opportunity)) or 0
    return AnalyticsRead(
        users=await session.scalar(select(func.count()).select_from(TelegramUser)) or 0,
        active_users=await session.scalar(
            select(func.count()).select_from(TelegramUser).where(TelegramUser.is_active.is_(True))
        )
        or 0,
        personal_matches=await session.scalar(select(func.count()).select_from(UserOpportunity)) or 0,
        scanned=total,
        filtered=global_counts.get(OpportunityStatus.FILTERED, 0),
        recommended=personal_counts.get(OpportunityStatus.RECOMMENDED, 0),
        approved=personal_counts.get(OpportunityStatus.APPROVED, 0),
        contacted=personal_counts.get(OpportunityStatus.CONTACTED, 0),
        replied=personal_counts.get(OpportunityStatus.REPLIED, 0),
        interviews=personal_counts.get(OpportunityStatus.INTERVIEW, 0),
        won=personal_counts.get(OpportunityStatus.WON, 0),
    )


@router.post("/collect/{source_name}")
async def collect_source(source_name: str, request: Request) -> dict:
    runtime = request.app.state.runtime
    source = next(
        (item for item in runtime.sources if item.name == source_name and item.type != "telegram"), None
    )
    if not source:
        raise HTTPException(404, "Enabled web source not found")
    await runtime.collector_runner.run(source)
    return {"status": "completed", "source": source_name}
