from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ContentCategory, Opportunity, SourceOccurrence
from app.services.content_classifier import is_demand_category


@dataclass(frozen=True, slots=True)
class SourceQualitySnapshot:
    source: str
    total: int
    categories: dict[str, int]

    @property
    def opportunity_count(self) -> int:
        return sum(
            count
            for category, count in self.categories.items()
            if is_demand_category(category)
        )

    @property
    def opportunity_share(self) -> float:
        return round(self.opportunity_count / self.total, 4) if self.total else 0


async def source_quality_snapshots(
    session: AsyncSession,
    *,
    source: str | None = None,
) -> list[SourceQualitySnapshot]:
    """Aggregate classified source occurrences without exposing message content."""
    query = (
        select(SourceOccurrence.source, Opportunity.content_category, func.count())
        .join(Opportunity, Opportunity.id == SourceOccurrence.opportunity_id)
        .group_by(SourceOccurrence.source, Opportunity.content_category)
    )
    if source:
        query = query.where(SourceOccurrence.source == source)
    rows = (await session.execute(query)).all()
    grouped: dict[str, dict[str, int]] = {}
    for source_name, category, count in rows:
        category_value = (category or ContentCategory.UNKNOWN).value
        grouped.setdefault(source_name, {})[category_value] = count
    return [
        SourceQualitySnapshot(
            source=source_name,
            total=sum(categories.values()),
            categories=categories,
        )
        for source_name, categories in sorted(grouped.items())
    ]
