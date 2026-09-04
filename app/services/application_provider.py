from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import SourceConfig
from app.models import Opportunity, TelegramUser, UserOpportunity


@dataclass(slots=True)
class ApplicationOutcome:
    provider: str
    status: str
    title: str
    message: str
    external_url: str | None = None
    resume_title: str | None = None
    command: dict | None = None
    error_code: str | None = None

    def payload(self) -> dict:
        return asdict(self)


class ApplicationProvider(ABC):
    @abstractmethod
    async def submit(
        self,
        session: AsyncSession,
        user: TelegramUser,
        match: UserOpportunity,
        opportunity: Opportunity,
        source: SourceConfig,
        idempotency_key: str,
    ) -> ApplicationOutcome:
        raise NotImplementedError
