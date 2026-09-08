"""Public project listings with full descriptions and no automatic application."""

import asyncio
import json
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from app.collectors.base import JobSource
from app.schemas import RawOpportunity


def rubles(text):
    match = re.search(r"(\d[\d\s\u00a0]*)\s*(?:₽|руб)", text, re.I)
    return float(re.sub(r"\s", "", match.group(1))) if match else None


def relative_date(text, now):
    units = [(r"(\d+)\s*(?:день|дня|дней)", 86400), (r"(\d+)\s*час", 3600), (r"(\d+)\s*минут", 60)]
    seconds = sum(int(m.group(1)) * factor for pattern, factor in units for m in re.finditer(pattern, text))
    return now - timedelta(seconds=seconds) if seconds else None


class FLSource(JobSource):
    async def fetch_new(self):
        items = self.parse_listing(await self.get_text(self.config.url or "https://www.fl.ru/projects/"))
        if not items:
            raise ValueError("FL listing has no recognizable projects")
        semaphore = asyncio.Semaphore(2)

        async def enrich(raw):
            async with semaphore:
                detail = await self.get_text(raw.source_url)
            soup = BeautifulSoup(detail, "html.parser")
            for script in soup.select('script[type="application/ld+json"]'):
                try:
                    data = json.loads(script.get_text())
                except ValueError:
                    continue
                if (
                    isinstance(data, dict)
                    and data.get("@type") in {"Product", "JobPosting"}
                    and data.get("description")
                ):
                    description = BeautifulSoup(data["description"], "html.parser").get_text("\n", strip=True)
                    return raw.model_copy(
                        update={"description": description, "raw_text": f"{raw.title}\n{description}"}
                    )
            raise ValueError(f"FL project description unavailable: {raw.external_id}")

        results = await asyncio.gather(*(enrich(raw) for raw in items), return_exceptions=True)
        self.fetch_errors = [
            f"{raw.external_id}: {type(result).__name__}"
            for raw, result in zip(items, results, strict=True)
            if isinstance(result, Exception)
        ]
        valid = [result for result in results if not isinstance(result, Exception)]
        if not valid:
            raise ValueError("No full project descriptions could be fetched")
        return valid

    def parse_listing(self, html):
        now = datetime.now(UTC)
        result = []
        for card in BeautifulSoup(html, "html.parser").select('[id^="project-item"]')[
            : int(self.config.options.get("limit", 30))
        ]:
            title = card.select_one("h2 a[href]")
            if not title or not re.match(r"/projects/\d+/", title.get("href", "")):
                continue
            price = card.select_one(".b-post__price")
            foot = card.select_one(".b-post__foot")
            desc = card.select_one(".b-post__body")
            name = title.get_text(" ", strip=True)
            description = desc.get_text(" ", strip=True) if desc else ""
            budget = rubles(price.get_text(" ", strip=True)) if price else None
            label = card.select_one(".b-post__bold")
            result.append(
                RawOpportunity(
                    source=self.config.name,
                    source_type="web",
                    external_id=re.search(r"/projects/(\d+)/", title["href"]).group(1),
                    title=name,
                    description=description,
                    raw_text=f"{name}\n{description}",
                    source_url=urljoin("https://www.fl.ru", title["href"]),
                    budget_min=budget,
                    budget_max=budget,
                    currency="RUB" if budget is not None else None,
                    employment_type="project" if label and label.get_text(strip=True) == "Заказ" else None,
                    published_at=relative_date(foot.get_text(" ", strip=True), now) if foot else None,
                    apply_mode=self.config.apply_mode,
                    metadata={"publication_time_approximate": True, "source_content_policy": "demand_only"},
                )
            )
        return result


class FreelanceRuSource(JobSource):
    async def fetch_new(self):
        items = self.parse_listing(await self.get_text(self.config.url or "https://freelance.ru/task/"))
        if not items:
            raise ValueError("Freelance.ru listing has no recognizable projects")
        semaphore = asyncio.Semaphore(2)

        async def enrich(raw):
            async with semaphore:
                html = await self.get_text(raw.source_url)
            section = BeautifulSoup(html, "html.parser").select_one(".tv-hero")
            if section is None:
                raise ValueError(f"Freelance.ru description unavailable: {raw.external_id}")
            for node in section.select(".tv-hero__top, h1"):
                node.decompose()
            description = section.get_text("\n", strip=True)
            return raw.model_copy(
                update={"description": description, "raw_text": f"{raw.title}\n{description}"}
            )

        results = await asyncio.gather(*(enrich(raw) for raw in items), return_exceptions=True)
        self.fetch_errors = [
            f"{raw.external_id}: {type(result).__name__}"
            for raw, result in zip(items, results, strict=True)
            if isinstance(result, Exception)
        ]
        valid = [result for result in results if not isinstance(result, Exception)]
        if not valid:
            raise ValueError("No full project descriptions could be fetched")
        return valid

    def parse_listing(self, html):
        result = []
        for card in BeautifulSoup(html, "html.parser").select(".task-card")[
            : int(self.config.options.get("limit", 25))
        ]:
            title = card.select_one(".task-card__title-link")
            if not title or not re.fullmatch(r"/task/view/\d+", title.get("href", "")):
                continue
            date_node = card.select_one(".task-card__foot-item[title]")
            try:
                published = (
                    datetime.strptime(date_node["title"], "%d.%m.%Y %H:%M").replace(
                        tzinfo=ZoneInfo("Europe/Moscow")
                    )
                    if date_node
                    else None
                )
            except ValueError:
                published = None
            budget_node = card.select_one(".task-card__budget")
            budget_text = budget_node.get_text(" ", strip=True) if budget_node else ""
            budget = rubles(budget_text)
            desc = card.select_one(".task-card__desc")
            name = title.get_text(" ", strip=True)
            description = desc.get_text(" ", strip=True) if desc else ""
            result.append(
                RawOpportunity(
                    source=self.config.name,
                    source_type="web",
                    external_id=title["href"].rsplit("/", 1)[-1],
                    title=name,
                    description=description,
                    raw_text=f"{name}\n{description}",
                    source_url=urljoin("https://freelance.ru", title["href"]),
                    budget_min=budget,
                    budget_max=budget,
                    currency="RUB" if budget is not None else None,
                    employment_type="project" if "/ заказ" in budget_text else None,
                    published_at=published,
                    apply_mode=self.config.apply_mode,
                    metadata={"source_content_policy": "demand_only", "budget_display": budget_text},
                )
            )
        return result
