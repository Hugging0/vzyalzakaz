from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from app.collectors.base import JobSource
from app.config import AppSettings, SourceConfig
from app.integrations.hh.collector import HHCollector
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
            keywords = self.config.options.get("keywords", ["python", "ai", "llm", "automation"])
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
        data = await self.get_json(self.config.url or "https://jobicy.com/api/v2/remote-jobs", params=params)
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


class HimalayasSource(JobSource):
    async def fetch_new(self) -> list[RawOpportunity]:
        data = await self.get_json(
            self.config.url or "https://himalayas.app/jobs/api",
            params={"limit": min(int(self.config.options.get("limit", 20)), 20)},
        )
        jobs = data.get("jobs", []) if isinstance(data, dict) else []
        return [
            RawOpportunity(
                source=self.config.name,
                source_type="api",
                external_id=str(job.get("guid") or job.get("applicationLink")),
                title=job.get("title", ""),
                description=_text(job.get("description") or job.get("excerpt")),
                raw_text=f"{job.get('title', '')}\n{_text(job.get('description') or job.get('excerpt'))}",
                source_url=job.get("applicationLink") or job.get("guid"),
                company=job.get("companyName"),
                budget_min=job.get("minSalary"),
                budget_max=job.get("maxSalary"),
                currency=job.get("currency"),
                employment_type=job.get("employmentType"),
                remote=True,
                country=", ".join(job.get("locationRestrictions") or []) or "Worldwide",
                skills=(job.get("categories") or []) + (job.get("parentCategories") or []),
                published_at=_date(job.get("pubDate")),
                apply_mode=self.config.apply_mode,
            )
            for job in jobs
            if isinstance(job, dict) and (job.get("guid") or job.get("applicationLink"))
        ]


class FreelancerSource(JobSource):
    async def fetch_new(self) -> list[RawOpportunity]:
        data = await self.get_json(
            self.config.url or "https://www.freelancer.com/api/projects/0.1/projects/active/",
            params={
                "limit": min(int(self.config.options.get("limit", 50)), 100),
                "full_description": "true",
                "job_details": "true",
                "sort_field": "time_updated",
            },
        )
        projects = (data.get("result") or {}).get("projects", []) if isinstance(data, dict) else []
        results = []
        for project in projects:
            if not isinstance(project, dict) or not project.get("id"):
                continue
            description = _text(project.get("description") or project.get("preview_description"))
            currency = project.get("currency") or {}
            budget = project.get("budget") or {}
            location = project.get("location") or {}
            country = location.get("country") or {}
            seo_url = (project.get("seo_url") or "").lstrip("/")
            source_url = (
                f"https://www.freelancer.com/projects/{seo_url}"
                if seo_url
                else f"https://www.freelancer.com/projects/{project['id']}"
            )
            results.append(
                RawOpportunity(
                    source=self.config.name,
                    source_type="api",
                    external_id=str(project["id"]),
                    title=(project.get("title") or "").strip(),
                    description=description,
                    raw_text=f"{project.get('title', '')}\n{description}",
                    source_url=source_url,
                    budget_min=budget.get("minimum"),
                    budget_max=budget.get("maximum"),
                    currency=currency.get("code"),
                    employment_type=project.get("type") or "freelance",
                    remote=not bool(project.get("local")),
                    country=country.get("name") or country.get("code"),
                    skills=[job.get("name") for job in project.get("jobs") or [] if job.get("name")],
                    published_at=_date(project.get("time_submitted") or project.get("submitdate")),
                    apply_mode=self.config.apply_mode,
                )
            )
        return results


class WorkingNomadsSource(JobSource):
    async def fetch_new(self) -> list[RawOpportunity]:
        data = await self.get_json(self.config.url or "https://www.workingnomads.com/api/exposed_jobs/")
        jobs = data if isinstance(data, list) else []
        limit = int(self.config.options.get("limit", 100))
        return [
            RawOpportunity(
                source=self.config.name,
                source_type="api",
                external_id=str(job.get("url")),
                title=job.get("title", ""),
                description=_text(job.get("description")),
                raw_text=f"{job.get('title', '')}\n{_text(job.get('description'))}",
                source_url=job.get("url"),
                company=job.get("company_name"),
                employment_type="remote",
                remote=True,
                country=job.get("location"),
                skills=[tag.strip() for tag in (job.get("tags") or "").split(",") if tag.strip()],
                published_at=_date(job.get("pub_date")),
                apply_mode=self.config.apply_mode,
            )
            for job in jobs[:limit]
            if isinstance(job, dict) and job.get("url")
        ]


class ProBloggerSource(JobSource):
    async def fetch_new(self) -> list[RawOpportunity]:
        html = await self.get_text(self.config.url or "https://problogger.com/jobs/")
        soup = BeautifulSoup(html, "html.parser")
        results = []
        for row in soup.select(".wpjb-job-list .wpjb-grid-row"):
            title_link = row.select_one(".wpjb-col-title .wpjb-line-major a[href]")
            if not title_link:
                continue
            title = title_link.get_text(" ", strip=True)
            source_url = title_link.get("href")
            company_node = row.select_one(".wpjb-col-title .wpjb-sub")
            location_node = row.select_one(".wpjb-col-location .wpjb-line-major")
            job_type_node = row.select_one(".wpjb-col-location .wpjb-sub")
            category_node = row.select_one(".custom-category-col .wpjb-line-major")
            company = company_node.get_text(" ", strip=True) if company_node else None
            location = location_node.get_text(" ", strip=True) if location_node else None
            job_type = job_type_node.get_text(" ", strip=True) if job_type_node else None
            category = category_node.get_text(" ", strip=True) if category_node else None
            details = " · ".join(value for value in (company, location, job_type, category) if value)
            results.append(
                RawOpportunity(
                    source=self.config.name,
                    source_type="web",
                    external_id=str(source_url),
                    title=title,
                    description=details,
                    raw_text=f"{title}\n{details}",
                    source_url=source_url,
                    company=company,
                    employment_type=job_type or "freelance",
                    remote=(location or "").lower() in {"remote", "anywhere", "worldwide"},
                    country=location,
                    skills=[category] if category else [],
                    apply_mode=self.config.apply_mode,
                )
            )
        return results


class GenericRSSSource(JobSource):
    async def fetch_new(self) -> list[RawOpportunity]:
        xml = await self.get_text(self.config.url or "")
        root = ElementTree.fromstring(xml)
        items = root.findall("./channel/item")
        limit = int(self.config.options.get("limit", 100))
        configured_skills = self.config.options.get("skills") or []
        results = []
        for item in items[:limit]:
            title = _text(item.findtext("title"))
            description = _text(
                item.findtext("description")
                or item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
            )
            link = item.findtext("link")
            guid = item.findtext("guid") or link or title
            if not title or not guid:
                continue
            published = item.findtext("pubDate")
            try:
                published_at = parsedate_to_datetime(published) if published else None
            except (TypeError, ValueError):
                published_at = None
            categories = [
                _text(category.text) for category in item.findall("category") if _text(category.text)
            ]
            raw_text = f"{title}\n{description}"
            normalized = raw_text.lower()
            remote = bool(self.config.options.get("remote")) or any(
                marker in normalized for marker in ("remote", "anywhere", "worldwide")
            )
            results.append(
                RawOpportunity(
                    source=self.config.name,
                    source_type="rss",
                    external_id=str(guid),
                    title=title,
                    description=description,
                    raw_text=raw_text,
                    source_url=link,
                    employment_type=self.config.options.get("employment_type"),
                    remote=remote,
                    skills=[*configured_skills, *categories],
                    published_at=published_at,
                    apply_mode=self.config.apply_mode,
                )
            )
        return results


COLLECTOR_REGISTRY: dict[str, type[JobSource]] = {
    "hh": HHCollector,
    "remotive": RemotiveSource,
    "remoteok": RemoteOKSource,
    "arbeitnow": ArbeitnowSource,
    "hackernews": HackerNewsSource,
    "jobicy": JobicySource,
    "weworkremotely": WeWorkRemotelySource,
    "himalayas": HimalayasSource,
    "freelancer": FreelancerSource,
    "working_nomads": WorkingNomadsSource,
    "problogger": ProBloggerSource,
    "generic_rss": GenericRSSSource,
}


def create_collector(config: SourceConfig, settings: AppSettings | None = None) -> JobSource:
    try:
        collector_class = COLLECTOR_REGISTRY[config.collector]
    except KeyError as exc:
        raise ValueError(f"Unknown web collector: {config.collector}") from exc
    return collector_class(config, settings)
