from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.collectors.web import (
    COLLECTOR_REGISTRY,
    FreelancerSource,
    GenericRSSSource,
    HimalayasSource,
    JobicySource,
    ProBloggerSource,
    RemotiveSource,
    WorkingNomadsSource,
)
from app.config import AppSettings, SourceConfig


def test_every_enabled_web_source_has_a_registered_collector() -> None:
    sources = AppSettings(config_dir=Path("config")).load_sources()

    enabled_web_sources = [source for source in sources if source.enabled and source.type != "telegram"]

    assert len(sources) == 186
    assert len({source.name for source in sources}) == len(sources)
    assert all(source.collector in COLLECTOR_REGISTRY for source in enabled_web_sources)
    assert all(not source.enabled for source in sources if source.collector == "pending")


@pytest.mark.asyncio
async def test_jobicy_source_maps_design_job() -> None:
    source = JobicySource(
        SourceConfig(name="jobicy_design", type="api", collector="jobicy", options={"limit": 2})
    )
    source.get_json = AsyncMock(
        return_value={
            "jobs": [
                {
                    "id": 42,
                    "jobTitle": "Video editor",
                    "jobDescription": "<p>Reels and motion</p>",
                    "url": "https://jobicy.com/jobs/42",
                    "companyName": "Studio",
                    "jobIndustry": ["Creative & Design"],
                    "jobType": ["Contract"],
                    "jobGeo": "Anywhere",
                    "pubDate": "2026-08-30T10:00:00+00:00",
                }
            ]
        }
    )

    items = await source.fetch_new()

    assert items[0].title == "Video editor"
    assert items[0].skills == ["Creative & Design"]
    assert items[0].remote is True


@pytest.mark.asyncio
async def test_remotive_source_passes_category_and_limit() -> None:
    source = RemotiveSource(
        SourceConfig(
            name="remotive_marketing",
            type="api",
            collector="remotive",
            options={"category": "marketing", "limit": 30},
        )
    )
    source.get_json = AsyncMock(return_value={"jobs": []})

    await source.fetch_new()

    assert source.get_json.await_args.kwargs["params"] == {"category": "marketing", "limit": 30}


@pytest.mark.asyncio
async def test_himalayas_source_maps_public_api_job() -> None:
    source = HimalayasSource(
        SourceConfig(name="himalayas", type="api", collector="himalayas", options={"limit": 50})
    )
    source.get_json = AsyncMock(
        return_value={
            "jobs": [
                {
                    "guid": "job-1",
                    "title": "Product designer",
                    "description": "<p>Design systems</p>",
                    "applicationLink": "https://himalayas.app/jobs/1",
                    "companyName": "Studio",
                    "employmentType": "Contractor",
                    "minSalary": 50,
                    "maxSalary": 80,
                    "currency": "USD",
                    "locationRestrictions": ["Worldwide"],
                    "categories": ["Design"],
                    "parentCategories": ["Creative"],
                    "pubDate": 1_788_000_000,
                }
            ]
        }
    )

    items = await source.fetch_new()

    assert items[0].external_id == "job-1"
    assert items[0].description == "Design systems"
    assert items[0].skills == ["Design", "Creative"]
    assert source.get_json.await_args.kwargs["params"] == {"limit": 20}


@pytest.mark.asyncio
async def test_freelancer_source_maps_public_project() -> None:
    source = FreelancerSource(
        SourceConfig(name="freelancer_com", type="api", collector="freelancer")
    )
    source.get_json = AsyncMock(
        return_value={
            "result": {
                "projects": [
                    {
                        "id": 42,
                        "title": " Python automation ",
                        "description": "<p>Build an agent</p>",
                        "seo_url": "python/python-automation",
                        "currency": {"code": "USD"},
                        "budget": {"minimum": 100, "maximum": 300},
                        "type": "fixed",
                        "local": False,
                        "location": {"country": {"name": "United States"}},
                        "jobs": [{"name": "Python"}, {"name": "Automation"}],
                        "time_submitted": 1_788_000_000,
                    }
                ]
            }
        }
    )

    items = await source.fetch_new()

    assert items[0].title == "Python automation"
    assert items[0].source_url == "https://www.freelancer.com/projects/python/python-automation"
    assert items[0].budget_min == 100
    assert items[0].skills == ["Python", "Automation"]


@pytest.mark.asyncio
async def test_working_nomads_source_uses_url_as_stable_id() -> None:
    source = WorkingNomadsSource(
        SourceConfig(name="working_nomads", type="api", collector="working_nomads")
    )
    source.get_json = AsyncMock(
        return_value=[
            {
                "title": "Motion designer",
                "company_name": "Studio",
                "description": "<p>Video and 3D</p>",
                "location": "WORLDWIDE",
                "url": "https://www.workingnomads.com/job/go/123/",
                "pub_date": "2026-08-31T12:04:17-04:00",
                "tags": "video, 3d, motion",
            }
        ]
    )

    items = await source.fetch_new()

    assert items[0].external_id == "https://www.workingnomads.com/job/go/123/"
    assert items[0].skills == ["video", "3d", "motion"]
    assert items[0].remote is True


@pytest.mark.asyncio
async def test_problogger_source_maps_public_listing() -> None:
    source = ProBloggerSource(
        SourceConfig(name="problogger_jobs", type="web", collector="problogger")
    )
    source.get_text = AsyncMock(
        return_value="""
        <div class="wpjb-job-list">
          <div class="wpjb-grid-row">
            <div class="wpjb-col-title">
              <span class="wpjb-line-major"><a href="https://problogger.com/jobs/job/1/">Writer</a></span>
              <span class="wpjb-sub">Publisher</span>
            </div>
            <div class="wpjb-col-location">
              <span class="wpjb-line-major">Remote</span><span class="wpjb-sub">Freelance</span>
            </div>
            <div class="custom-category-col"><span class="wpjb-line-major">Copywriting</span></div>
          </div>
        </div>
        """
    )

    items = await source.fetch_new()

    assert items[0].title == "Writer"
    assert items[0].company == "Publisher"
    assert items[0].skills == ["Copywriting"]
    assert items[0].remote is True


@pytest.mark.asyncio
async def test_generic_rss_source_maps_categories_and_remote_signal() -> None:
    source = GenericRSSSource(
        SourceConfig(
            name="python_org_jobs",
            type="rss",
            collector="generic_rss",
            options={"skills": ["Python"], "limit": 10},
        )
    )
    source.get_text = AsyncMock(
        return_value="""
        <rss><channel><item>
          <title>Backend Engineer</title>
          <link>https://example.com/jobs/1</link>
          <guid>job-1</guid>
          <description><![CDATA[<p>Remote Python role</p>]]></description>
          <category>Backend</category>
          <pubDate>Tue, 01 Sep 2026 10:00:00 +0000</pubDate>
        </item></channel></rss>
        """
    )

    items = await source.fetch_new()

    assert items[0].external_id == "job-1"
    assert items[0].description == "Remote Python role"
    assert items[0].skills == ["Python", "Backend"]
    assert items[0].remote is True
