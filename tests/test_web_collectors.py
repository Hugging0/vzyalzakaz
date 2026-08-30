from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.collectors.web import JobicySource, RemotiveSource
from app.config import SourceConfig


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
