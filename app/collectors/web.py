from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from app.collectors.base import JobSource
from app.config import SourceConfig
from app.schemas import RawOpportunity


def _text(html: str | None) -> str:
    return BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)


def _date(value: str | int | float | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


class HHSource(JobSource):
    async def fetch_new(self) -> list[RawOpportunity]:
        data = await self.get_json(
            self.config.url or "https://api.hh.ru/vacancies",
            params={
                "text": self.config.options.get("query", "Python OR automation OR LLM"),
                "period": 1,
                "per_page": self.config.options.get("limit", 50),
                "order_by": "publication_time",
            },
        )
        items = data.get("items", []) if isinstance(data, dict) else []
        results = []
        for item in items:
            snippet = item.get("snippet") or {}
            requirement = _text(snippet.get("requirement"))
            responsibility = _text(snippet.get("responsibility"))
            results.append(
                RawOpportunity(
                    source=self.config.name,
                    source_type="web",
                    external_id=str(item["id"]),
                    title=item.get("name", ""),
                    description=f"{requirement} {responsibility}".strip(),
                    raw_text=f"{item.get('name', '')}\n{requirement}\n{responsibility}",
                    source_url=item.get("alternate_url"),
                    company=(item.get("employer") or {}).get("name"),
                    budget_min=(item.get("salary") or {}).get("from"),
                    budget_max=(item.get("salary") or {}).get("to"),
                    currency=(
                        "RUB"
                        if (item.get("salary") or {}).get("currency") == "RUR"
                        else (item.get("salary") or {}).get("currency")
                    ),
                    employment_type=(item.get("schedule") or {}).get("name"),
                    remote=(item.get("schedule") or {}).get("id") == "remote",
                    published_at=_date(item.get("published_at")),
                    apply_mode=self.config.apply_mode,
                )
            )
        return results


class RemotiveSource(JobSource):
    async def fetch_new(self) -> list[RawOpportunity]:
        params = {"limit": self.config.options.get("limit", 100)}
        if query := self.config.options.get("query"):
            params["search"] = query
        if category := self.config.options.get("category"):
            params["category"] = category
        data = await self.get_json(
            self.config.url or "https://remotive.com/api/remote-jobs",
            params=params,
        )
        jobs = data.get("jobs", []) if isinstance(data, dict) else []
        return [
            RawOpportunity(
                source=self.config.name,
                source_type="api",
                external_id=str(job["id"]),
                title=job.get("title", ""),
                description=_text(job.get("description")),
                raw_text=f"{job.get('title', '')}\n{_text(job.get('description'))}",
                source_url=job.get("url"),
                company=job.get("company_name"),
                employment_type=job.get("job_type"),
                remote=True,
                country=job.get("candidate_required_location"),
                skills=job.get("tags") or [],
                published_at=_date(job.get("publication_date")),
                apply_mode=self.config.apply_mode,
            )
            for job in jobs
        ]


class RemoteOKSource(JobSource):
    async def fetch_new(self) -> list[RawOpportunity]:
        data = await self.get_json(self.config.url or "https://remoteok.com/api")
        jobs = data[1:] if isinstance(data, list) and data and "id" not in data[0] else data
        return [
            RawOpportunity(
                source=self.config.name,
                source_type="api",
                external_id=str(job.get("id") or job.get("position", "")),
                title=job.get("position", ""),
                description=_text(job.get("description")),
                raw_text=f"{job.get('position', '')}\n{_text(job.get('description'))}",
                source_url=job.get("url") or job.get("apply_url"),
                company=job.get("company"),
                employment_type="remote",
                remote=True,
                country=job.get("location"),
                skills=job.get("tags") or [],
                published_at=_date(job.get("date") or job.get("epoch")),
                apply_mode=self.config.apply_mode,
            )
            for job in jobs
            if isinstance(job, dict) and (job.get("id") or job.get("position"))
        ]


class ArbeitnowSource(JobSource):
    async def fetch_new(self) -> list[RawOpportunity]:
        data = await self.get_json(self.config.url or "https://www.arbeitnow.com/api/job-board-api")
        jobs = data.get("data", []) if isinstance(data, dict) else []
        return [
            RawOpportunity(
                source=self.config.name,
                source_type="api",
                external_id=str(job.get("slug") or job.get("url")),
                title=job.get("title", ""),
                description=_text(job.get("description")),
                raw_text=f"{job.get('title', '')}\n{_text(job.get('description'))}",
                source_url=job.get("url"),
                company=job.get("company_name"),
                employment_type="remote" if job.get("remote") else "unknown",
                remote=job.get("remote"),
                country=job.get("location"),
                skills=job.get("tags") or [],
                published_at=_date(job.get("created_at")),
                apply_mode=self.config.apply_mode,
            )
            for job in jobs
        ]


class HackerNewsSource(JobSource):
    async def fetch_new(self) -> list[RawOpportunity]:
        query = self.config.options.get("query", "Ask HN: Who is hiring?")
        data = await self.get_json(
            self.config.url or "https://hn.algolia.com/api/v1/search_by_date",
            params={"query": query, "tags": "story", "hitsPerPage": 10},
        )
        hits = data.get("hits", []) if isinstance(data, dict) else []
        story = next(
            (hit for hit in hits if (hit.get("title") or "").lower().startswith("ask hn: who is hiring? (")),
            None,
        )
        if not story:
            return []
        thread = await self.get_json(f"https://hn.algolia.com/api/v1/items/{story['objectID']}")
        hits = thread.get("children", []) if isinstance(thread, dict) else []
        results = []
        for hit in hits:
            body = _text(hit.get("text"))
            if not body:
                continue
            normalized = body.lower()
            keywords = self.config.options.get(
                "keywords", ["python", "ai", "llm", "automation"]
            )
            if not any(word.lower() in normalized for word in keywords):
                continue
            object_id = str(hit.get("id"))
            results.append(
                RawOpportunity(
                    source=self.config.name,
                    source_type="web",
                    external_id=object_id,
                    title=body[:120].strip(),
                    description=body,
                    raw_text=body,
                    source_url=f"https://news.ycombinator.com/item?id={object_id}",
                    client_name=hit.get("author"),
                    remote="remote" in body.lower(),
                    published_at=_date(hit.get("created_at")),
                    apply_mode=self.config.apply_mode,
                )
            )
        return results


class WeWorkRemotelySource(JobSource):
    async def fetch_new(self) -> list[RawOpportunity]:
        xml = await self.get_text(
            self.config.url or "https://weworkremotely.com/categories/remote-programming-jobs.rss"
        )
        root = ElementTree.fromstring(xml)
        results = []
        for item in root.findall("./channel/item"):
            title = item.findtext("title") or ""
            description = _text(item.findtext("description"))
            link = item.findtext("link")
            guid = item.findtext("guid") or link or title
            published = item.findtext("pubDate")
            try:
                published_at = parsedate_to_datetime(published) if published else None
            except (TypeError, ValueError):
                published_at = None
            company, separator, role = title.partition(":")
            results.append(
                RawOpportunity(
                    source=self.config.name,
                    source_type="rss",
                    external_id=guid,
                    title=(role or title).strip(),
                    description=description,
                    raw_text=f"{title}\n{description}",
                    source_url=link,
                    company=company.strip() if separator else None,
                    employment_type="remote",
                    remote=True,
                    published_at=published_at,
                    apply_mode=self.config.apply_mode,
                )
            )
        return results


class JobicySource(JobSource):
    async def fetch_new(self) -> list[RawOpportunity]:
        params = {"count": self.config.options.get("limit", 100)}
        for key in ("industry", "geo", "tag"):
            if value := self.config.options.get(key):
                params[key] = value
        data = await self.get_json(
            self.config.url or "https://jobicy.com/api/v2/remote-jobs", params=params
        )
        jobs = data.get("jobs", []) if isinstance(data, dict) else []
        return [
            RawOpportunity(
                source=self.config.name,
                source_type="api",
                external_id=str(job.get("id") or job.get("jobSlug")),
                title=job.get("jobTitle", ""),
                description=_text(job.get("jobDescription") or job.get("jobExcerpt")),
                raw_text=f"{job.get('jobTitle', '')}\n{_text(job.get('jobDescription'))}",
                source_url=job.get("url"),
                company=job.get("companyName"),
                employment_type=", ".join(job.get("jobType") or []),
                remote=True,
                country=job.get("jobGeo"),
                skills=job.get("jobIndustry") or [],
                published_at=_date(job.get("pubDate")),
                apply_mode=self.config.apply_mode,
            )
            for job in jobs
            if isinstance(job, dict) and (job.get("id") or job.get("jobSlug"))
        ]


COLLECTOR_REGISTRY: dict[str, type[JobSource]] = {
    "hh": HHSource,
    "remotive": RemotiveSource,
    "remoteok": RemoteOKSource,
    "arbeitnow": ArbeitnowSource,
    "hackernews": HackerNewsSource,
    "jobicy": JobicySource,
    "weworkremotely": WeWorkRemotelySource,
}


def create_collector(config: SourceConfig) -> JobSource:
    try:
        collector_class = COLLECTOR_REGISTRY[config.collector]
    except KeyError as exc:
        raise ValueError(f"Unknown web collector: {config.collector}") from exc
    return collector_class(config)
