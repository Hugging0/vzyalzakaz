from __future__ import annotations

from datetime import datetime

from bs4 import BeautifulSoup

from app.config import SourceConfig
from app.schemas import RawOpportunity


def map_vacancy(item: dict, source: SourceConfig, *, allow_external_llm: bool) -> RawOpportunity:
    description = _text(item.get("description"))
    if not description:
        snippet = item.get("snippet") or {}
        description = " ".join(
            value
            for value in (_text(snippet.get("requirement")), _text(snippet.get("responsibility")))
            if value
        )
    salary = item.get("salary") or {}
    schedule = item.get("schedule") or {}
    area = item.get("area") or {}
    employer = item.get("employer") or {}
    employment = item.get("employment") or {}
    key_skills = [value.get("name") for value in item.get("key_skills") or [] if value.get("name")]
    external_id = str(item["id"])
    source_url = item.get("alternate_url") or f"https://hh.ru/vacancy/{external_id}"
    return RawOpportunity(
        source=source.name,
        source_type="api",
        external_id=external_id,
        title=(item.get("name") or "").strip(),
        description=description,
        raw_text=f"{item.get('name', '')}\n{description}".strip(),
        source_url=source_url,
        company=employer.get("name"),
        budget_min=salary.get("from"),
        budget_max=salary.get("to"),
        currency="RUB" if salary.get("currency") == "RUR" else salary.get("currency"),
        employment_type=employment.get("id") or schedule.get("id"),
        remote=schedule.get("id") == "remote",
        country=area.get("name"),
        skills=key_skills,
        technologies=key_skills,
        published_at=_date(item.get("published_at")),
        edited_at=_date(item.get("initial_created_at") or item.get("created_at")),
        apply_mode="api_allowed",
        metadata={
            "external_ai_allowed": allow_external_llm,
            "source_policy": "hh_api",
            "source_content_policy": "demand_only",
            "provider_metadata": {
                "provider": "hh",
                "alternate_url": source_url,
                "apply_alternate_url": item.get("apply_alternate_url"),
                "archived": bool(item.get("archived")),
                "relations": item.get("relations") or [],
                "response_letter_required": bool(item.get("response_letter_required")),
                "has_test": bool(item.get("test")),
                "negotiations_url": item.get("negotiations_url"),
                "suitable_resumes_url": item.get("suitable_resumes_url"),
            },
        },
    )


def _text(value: str | None) -> str:
    return BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
