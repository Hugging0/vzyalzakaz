from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AppSettings, SourceConfig, get_settings
from app.integrations.hh.client import HHClient
from app.integrations.hh.errors import HHError
from app.integrations.hh.mapper import map_vacancy
from app.models import Opportunity, OpportunityStatus, UserOpportunity
from app.schemas import RawOpportunity


class HHCollector:
    """Collects global, candidate-neutral HH vacancies through the official API."""

    def __init__(self, config: SourceConfig, settings: AppSettings | None = None):
        self.config = config
        self.settings = settings or get_settings()

    async def fetch_new(self) -> list[RawOpportunity]:
        return await self._fetch(None)

    async def fetch_incremental(self, session: AsyncSession) -> list[RawOpportunity]:
        return await self._fetch(session)

    async def _fetch(self, session: AsyncSession | None) -> list[RawOpportunity]:
        client = HHClient(self.settings)
        page = 0
        max_pages = min(max(int(self.config.options.get("max_pages", 3)), 1), 20)
        per_page = min(max(int(self.config.options.get("per_page", 50)), 1), 100)
        period = min(max(int(self.config.options.get("period_days", 2)), 1), 30)
        query = str(self.config.options.get("query") or "").strip()
        results: list[RawOpportunity] = []
        seen: set[str] = set()
        while page < max_pages:
            params = {
                "page": page,
                "per_page": per_page,
                "period": period,
                "order_by": "publication_time",
                "search_field": "name",
            }
            if query:
                params["text"] = query
            payload = await client.search_vacancies(params)
            items = payload.get("items") or []
            page_ids = {str(item.get("id") or "") for item in items if item.get("id")}
            persisted = set()
            if session is not None and page_ids:
                persisted = set(
                    await session.scalars(
                        select(Opportunity.external_id).where(
                            Opportunity.source == self.config.name,
                            Opportunity.external_id.in_(page_ids),
                        )
                    )
                )
            for summary in items:
                external_id = str(summary.get("id") or "")
                if not external_id or external_id in seen or external_id in persisted:
                    continue
                seen.add(external_id)
                detail = await client.vacancy(external_id)
                results.append(
                    map_vacancy(
                        detail,
                        self.config,
                        allow_external_llm=self.settings.hh_allow_external_llm,
                    )
                )
            page += 1
            if page >= int(payload.get("pages") or 0) or not items:
                break
        return results

    async def reconcile(self, session: AsyncSession) -> None:
        """Bounded recheck keeps recently persisted HH records current and hides closed jobs."""
        limit = min(max(int(self.config.options.get("recheck_limit", 20)), 0), 100)
        if not limit:
            return
        opportunities = (
            await session.scalars(
                select(Opportunity)
                .where(
                    Opportunity.source == self.config.name,
                    Opportunity.status != OpportunityStatus.FILTERED,
                )
                .order_by(Opportunity.source_checked_at.asc())
                .limit(limit)
            )
        ).all()
        client = HHClient(self.settings)
        for opportunity in opportunities:
            try:
                detail = await client.vacancy(opportunity.external_id)
                closed = bool(detail.get("archived"))
                opportunity.provider_metadata = {
                    **(opportunity.provider_metadata or {}),
                    "archived": closed,
                    "relations": detail.get("relations") or [],
                }
            except HHError as exc:
                if exc.code != "vacancy_not_found":
                    continue
                closed = True
            opportunity.source_checked_at = datetime.now(UTC)
            if closed:
                opportunity.status = OpportunityStatus.FILTERED
                opportunity.skip_reason = "source_closed"
                await session.execute(
                    delete(UserOpportunity).where(
                        UserOpportunity.opportunity_id == opportunity.id,
                        UserOpportunity.status == OpportunityStatus.RECOMMENDED,
                    )
                )
        await session.commit()
