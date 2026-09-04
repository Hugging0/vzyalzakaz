from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AppSettings, SourceConfig
from app.integrations.hh.application_provider import HHApplicationProvider
from app.models import ApplicationCommand, Opportunity, TelegramUser, UserOpportunity
from app.services.application_commands import command_payload, create_application_command
from app.services.application_provider import ApplicationOutcome, ApplicationProvider


class BrowserExtensionApplicationProvider(ApplicationProvider):
    def __init__(self, settings: AppSettings):
        self.settings = settings

    async def submit(
        self,
        session: AsyncSession,
        user: TelegramUser,
        match: UserOpportunity,
        opportunity: Opportunity,
        source: SourceConfig,
        idempotency_key: str,
    ) -> ApplicationOutcome:
        del source
        command = await create_application_command(
            session, self.settings, user, match, opportunity, idempotency_key
        )
        return _command_outcome(command, opportunity.source_url)


class ApplicationService:
    def __init__(self, settings: AppSettings):
        self.settings = settings

    def _source(self, opportunity: Opportunity) -> SourceConfig | None:
        return next(
            (item for item in self.settings.load_sources() if item.name == opportunity.source),
            None,
        )

    async def submit(
        self,
        session: AsyncSession,
        user: TelegramUser,
        match: UserOpportunity,
        opportunity: Opportunity,
        idempotency_key: str,
    ) -> ApplicationOutcome:
        source = self._source(opportunity)
        if source is None:
            return _manual_outcome(opportunity.source_url)
        provider_id = source.application_provider
        if provider_id is None and source.submission_type == "browser_extension":
            provider_id = "browser_extension"
        providers: dict[str, ApplicationProvider] = {
            "hh": HHApplicationProvider(self.settings),
            "browser_extension": BrowserExtensionApplicationProvider(self.settings),
        }
        provider = providers.get(provider_id or "")
        if provider is None:
            return _manual_outcome(opportunity.source_url)
        return await provider.submit(session, user, match, opportunity, source, idempotency_key)

    async def status(
        self,
        session: AsyncSession,
        user: TelegramUser,
        match: UserOpportunity,
        opportunity: Opportunity,
    ) -> ApplicationOutcome:
        source = self._source(opportunity)
        if source and source.application_provider == "hh":
            return await HHApplicationProvider(self.settings).status(session, user, match, opportunity)
        command = await session.scalar(
            select(ApplicationCommand)
            .where(
                ApplicationCommand.user_id == user.id,
                ApplicationCommand.user_opportunity_id == match.id,
            )
            .order_by(ApplicationCommand.created_at.desc())
            .limit(1)
        )
        if command:
            return _command_outcome(command, opportunity.source_url)
        if source and source.submission_type == "browser_extension":
            return ApplicationOutcome(
                "browser_extension",
                "ready",
                "Отклик в браузере",
                "Расширение заполнит форму и оставит отправку вам.",
                opportunity.source_url,
            )
        return _manual_outcome(opportunity.source_url)


def _manual_outcome(url: str | None) -> ApplicationOutcome:
    return ApplicationOutcome(
        "manual",
        "manual_only",
        "Отклик вручную",
        "Откройте площадку и отправьте текст.",
        url,
    )


def _command_outcome(command: ApplicationCommand, url: str | None) -> ApplicationOutcome:
    status = command.status.value
    message = {
        "queued": "Передаём отклик расширению.",
        "delivered": "Расширение получило задачу.",
        "waiting_for_auth": "Войдите на площадку и продолжите.",
        "partially_filled": "Дополните обязательные поля и проверьте форму.",
        "ready_for_review": "Проверьте форму и отправьте её на площадке.",
        "submitted": "Площадка подтвердила отклик.",
        "failed": "Не удалось подготовить форму.",
    }.get(status, "Расширение готовит форму.")
    return ApplicationOutcome(
        "browser_extension",
        status,
        "Форма готова" if status == "ready_for_review" else "Отклик в браузере",
        message,
        url,
        command=command_payload(command),
        error_code=command.error_code,
    )
