"""Split clearly structured multi-order Telegram digests without sharing contacts."""

import re

from sqlalchemy import select, update

from app.models import Opportunity, OpportunityStatus, UserOpportunity
from app.schemas import RawOpportunity

HEADING = re.compile(r"(?m)^[\s\u200b]*#[\w]+(?:[ \t]+#[\w]+)*[ \t]*$")
CONTACT = re.compile(r"@[A-Za-z][A-Za-z0-9_]{4,31}|https?://t\.me/\w+")
FOOTER = re.compile(r"(?im)^\s*Больше\s+\d+\s+вакансий.*", re.S)


def split_message_tasks(raw: RawOpportunity) -> list[RawOpportunity]:
    if raw.source_type != "telegram":
        return [raw]
    text = raw.raw_text or raw.description
    headings = list(HEADING.finditer(text))
    if not 2 <= len(headings) <= 20:
        return [raw]
    chunks = [
        text[h.start() : headings[i + 1].start() if i + 1 < len(headings) else len(text)].strip()
        for i, h in enumerate(headings)
    ]
    chunks = [FOOTER.sub("", chunk).strip() for chunk in chunks]
    # Never split a single vacancy with section hashtags and one shared contact.
    if not all(len(chunk) >= 40 and CONTACT.search(chunk) for chunk in chunks):
        return [raw]
    return [
        raw.model_copy(
            update={
                "external_id": f"{raw.external_id}:part:{i + 1}",
                "title": next(
                    (line.strip(" #") for line in chunk.splitlines()[1:] if len(line.strip()) > 5),
                    chunk[:180],
                )[:180],
                "description": chunk,
                "raw_text": chunk,
                "contact_username": None,
                "contact_email": None,
                "budget_min": None,
                "budget_max": None,
                "currency": None,
                "metadata": {**raw.metadata, "parent_external_id": raw.external_id, "task_index": i + 1},
            }
        )
        for i, chunk in enumerate(chunks)
    ]


async def process_message_tasks(session, pipeline, raw):
    parts = split_message_tasks(raw)
    results = [await pipeline.process(session, part) for part in parts]
    active_ids = {part.external_id for part in parts}
    existing = (
        await session.scalars(
            select(Opportunity).where(
                Opportunity.source == raw.source,
                (Opportunity.external_id == raw.external_id)
                | Opportunity.external_id.startswith(raw.external_id + ":part:"),
            )
        )
    ).all()
    for row in existing:
        if row.external_id in active_ids:
            continue
        row.status = OpportunityStatus.FILTERED
        row.skip_reason = "superseded_by_message_tasks"
        await session.execute(
            update(UserOpportunity)
            .where(
                UserOpportunity.opportunity_id == row.id,
                UserOpportunity.status == OpportunityStatus.RECOMMENDED,
            )
            .values(status=OpportunityStatus.FILTERED)
        )
    await session.commit()
    return results
