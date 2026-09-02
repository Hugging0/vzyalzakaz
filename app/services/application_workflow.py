from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ApplicationEvent, OpportunityStatus, UserOpportunity

ALLOWED_TRANSITIONS: dict[OpportunityStatus, set[OpportunityStatus]] = {
    OpportunityStatus.RECOMMENDED: {OpportunityStatus.APPROVED, OpportunityStatus.SKIPPED},
    OpportunityStatus.APPROVED: {
        OpportunityStatus.CONTACTED,
        OpportunityStatus.SKIPPED,
    },
    OpportunityStatus.CONTACTED: {
        OpportunityStatus.REPLIED,
        OpportunityStatus.LOST,
    },
    OpportunityStatus.REPLIED: {
        OpportunityStatus.INTERVIEW,
        OpportunityStatus.WON,
        OpportunityStatus.LOST,
    },
    OpportunityStatus.INTERVIEW: {OpportunityStatus.WON, OpportunityStatus.LOST},
    OpportunityStatus.SKIPPED: {OpportunityStatus.RECOMMENDED},
    OpportunityStatus.LOST: {OpportunityStatus.REPLIED},
    OpportunityStatus.WON: set(),
    OpportunityStatus.NEW: {OpportunityStatus.RECOMMENDED},
    OpportunityStatus.FILTERED: set(),
}


async def record_event(
    session: AsyncSession,
    match: UserOpportunity,
    event: str,
    *,
    actor: str,
    detail: str | None = None,
) -> None:
    session.add(
        ApplicationEvent(
            user_opportunity_id=match.id,
            user_id=match.user_id,
            event=event,
            detail=detail[:255] if detail else None,
            actor=actor,
        )
    )


async def transition_application(
    session: AsyncSession,
    match: UserOpportunity,
    target: OpportunityStatus,
    *,
    actor: str,
    detail: str | None = None,
) -> UserOpportunity:
    if match.status == target:
        return match
    if target not in ALLOWED_TRANSITIONS.get(match.status, set()):
        raise HTTPException(409, f"Нельзя изменить статус {match.status.value} на {target.value}")
    if target == OpportunityStatus.CONTACTED and not match.proposal:
        raise HTTPException(409, "Сначала подготовьте и проверьте текст отклика")
    match.status = target
    now = datetime.now(UTC)
    if target == OpportunityStatus.APPROVED:
        match.approved_at = now
    elif target == OpportunityStatus.CONTACTED:
        match.contacted_at = now
    await record_event(session, match, target.value, actor=actor, detail=detail)
    await session.commit()
    return match
