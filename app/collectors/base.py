from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod

import httpx

from app.config import SourceConfig
from app.schemas import RawOpportunity

logger = logging.getLogger(__name__)


class JobSource(ABC):
    def __init__(self, config: SourceConfig):
        self.config = config

    @abstractmethod
    async def fetch_new(self) -> list[RawOpportunity]:
        raise NotImplementedError

    async def get_json(self, url: str, **kwargs) -> dict | list:
        headers = {"User-Agent": "PersonalAIJobHunter/0.1 (self-hosted; polite polling)"}
        timeout = httpx.Timeout(20, connect=10)
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(
                    timeout=timeout, headers=headers, follow_redirects=True
                ) as client:
                    response = await client.get(url, **kwargs)
                    response.raise_for_status()
                    return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(2**attempt)
        raise RuntimeError(f"Source {self.config.name} failed after retries") from last_error

    async def get_text(self, url: str, **kwargs) -> str:
        headers = {"User-Agent": "PersonalAIJobHunter/0.1 (self-hosted; polite polling)"}
        timeout = httpx.Timeout(20, connect=10)
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(
                    timeout=timeout, headers=headers, follow_redirects=True
                ) as client:
                    response = await client.get(url, **kwargs)
                    response.raise_for_status()
                    return response.text
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(2**attempt)
        raise RuntimeError(f"Source {self.config.name} failed after retries") from last_error
