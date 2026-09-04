from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AppSettings, SourceConfig
from app.integrations.hh.client import HHClient
from app.integrations.hh.errors import ERROR_MESSAGES, HHError
from app.integrations.hh.oauth import access_token_for, connection_for_user, mark_reauth_required
from app.models import (
    ApplicationAttempt,
    ApplicationAttemptStatus,
    ApplicationCommand,
    ExternalConnectionStatus,
    Opportunity,
    OpportunityStatus,
    TelegramUser,
    UserOpportunity,
)
from app.services.application_commands import command_payload, create_application_command
from app.services.application_provider import ApplicationOutcome, ApplicationProvider
from app.services.application_workflow import record_event, transition_application


class HHApplicationProvider(ApplicationProvider):
    def __init__(self, settings: AppSettings, *, client: HHClient | None = None):
        self.settings = settings
        self.client = client or HHClient(settings)

    async def status(
        self,
        session: AsyncSession,
        user: TelegramUser,
        match: UserOpportunity,
        opportunity: Opportunity,
    ) -> ApplicationOutcome:
        connection = await connection_for_user(session, user.id)
        if connection is None or connection.status != ExternalConnectionStatus.CONNECTED:
            return ApplicationOutcome(
                "hh",
                "connection_required",
                "Подключите HH",
                "Авторизация нужна для отправки отклика.",
                opportunity.source_url,
            )
        resume = _selected_resume(connection.metadata_json, connection.selected_resume_id)
        if not resume:
            return ApplicationOutcome(
                "hh",
                "resume_required",
                "Выберите резюме",
                "Укажите основное резюме в разделе «Площадки».",
                opportunity.source_url,
            )
        attempt = await session.scalar(
            select(ApplicationAttempt).where(
                ApplicationAttempt.user_id == user.id,
                ApplicationAttempt.user_opportunity_id == match.id,
                ApplicationAttempt.provider == "hh",
            )
        )
        if attempt:
            outcome = _attempt_outcome(attempt, opportunity.source_url, resume.get("title"))
            if attempt.status == ApplicationAttemptStatus.EXTERNAL_ACTION_REQUIRED:
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
                    outcome.command = command_payload(command)
            return outcome
        return ApplicationOutcome(
            "hh",
            "ready",
            "Отклик через HH",
            "Проверьте текст — отправка начнётся только после нажатия.",
            opportunity.source_url,
            resume.get("title"),
        )

    async def submit(
        self,
        session: AsyncSession,
        user: TelegramUser,
        match: UserOpportunity,
        opportunity: Opportunity,
        source: SourceConfig,
        idempotency_key: str,
    ) -> ApplicationOutcome:
        if not match.proposal:
            return ApplicationOutcome(
                "hh",
                "proposal_required",
                "Сначала подготовьте текст",
                "Перед отправкой проверьте сопроводительное письмо.",
                opportunity.source_url,
            )
        same_request = await session.scalar(
            select(ApplicationAttempt).where(
                ApplicationAttempt.user_id == user.id,
                ApplicationAttempt.idempotency_key == idempotency_key,
            )
        )
        if same_request:
            if same_request.user_opportunity_id != match.id:
                return ApplicationOutcome(
                    "hh",
                    "failed",
                    "Отклик не отправлен",
                    "Этот запрос уже использован для другого отклика. Обновите страницу.",
                    opportunity.source_url,
                    error_code="idempotency_conflict",
                )
            return _attempt_outcome(
                same_request,
                opportunity.source_url,
                (same_request.result or {}).get("resume_title"),
            )
        existing = await session.scalar(
            select(ApplicationAttempt).where(
                ApplicationAttempt.user_id == user.id,
                ApplicationAttempt.user_opportunity_id == match.id,
                ApplicationAttempt.provider == "hh",
            )
        )
        if existing and existing.status not in {ApplicationAttemptStatus.FAILED}:
            resume_title = (existing.result or {}).get("resume_title")
            return _attempt_outcome(existing, opportunity.source_url, resume_title)

        connection = await connection_for_user(session, user.id)
        if connection is None or connection.status != ExternalConnectionStatus.CONNECTED:
            return ApplicationOutcome(
                "hh",
                "connection_required",
                "Подключите HH",
                "Авторизация нужна для отправки отклика.",
                opportunity.source_url,
            )
        resume = _selected_resume(connection.metadata_json, connection.selected_resume_id)
        if not resume:
            return ApplicationOutcome(
                "hh",
                "resume_required",
                "Выберите резюме",
                "Укажите основное резюме в разделе «Площадки».",
                opportunity.source_url,
            )

        attempt = existing or ApplicationAttempt(
            user_id=user.id,
            user_opportunity_id=match.id,
            provider="hh",
            idempotency_key=idempotency_key,
        )
        attempt.idempotency_key = idempotency_key
        attempt.status = ApplicationAttemptStatus.PROCESSING
        attempt.error_code = None
        attempt.detail = None
        attempt.result = {"resume_id": resume["id"], "resume_title": resume["title"]}
        if existing is None:
            session.add(attempt)
        await record_event(session, match, "hh_application_started", actor="web")
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            concurrent = await session.scalar(
                select(ApplicationAttempt).where(
                    ApplicationAttempt.user_id == user.id,
                    ApplicationAttempt.user_opportunity_id == match.id,
                    ApplicationAttempt.provider == "hh",
                )
            )
            if concurrent is None:
                raise
            return _attempt_outcome(
                concurrent,
                opportunity.source_url,
                (concurrent.result or {}).get("resume_title"),
            )

        try:
            access_token = await access_token_for(session, connection, self.settings, client=self.client)
            vacancy = await self.client.vacancy(opportunity.external_id, access_token)
            metadata = opportunity.provider_metadata or {}
            if vacancy.get("archived"):
                raise HHError("vacancy_not_found", ERROR_MESSAGES["vacancy_not_found"], 404)
            relations = vacancy.get("relations") or metadata.get("relations") or []
            if "got_response" in relations:
                return await self._already_applied(session, attempt, match, resume["title"], opportunity)
            if vacancy.get("test") or metadata.get("has_test"):
                return await self._external_action(
                    session, attempt, user, match, opportunity, source, resume["title"], "test_required"
                )
            suitable = await self.client.suitable_resumes(opportunity.external_id, access_token)
            suitable_items = suitable if isinstance(suitable, list) else suitable.get("items") or []
            suitable_ids = {
                str(item.get("id")) for item in suitable_items if isinstance(item, dict) and item.get("id")
            }
            if resume["id"] not in suitable_ids:
                raise HHError("resume_not_found", ERROR_MESSAGES["resume_not_found"], 409)
            if not (vacancy.get("negotiations_url") or metadata.get("negotiations_url")):
                return await self._external_action(
                    session, attempt, user, match, opportunity, source, resume["title"], "application_denied"
                )
            result = await self.client.apply(
                opportunity.external_id, resume["id"], match.proposal, access_token
            )
        except HHError as exc:
            if exc.code == "already_applied":
                return await self._already_applied(session, attempt, match, resume["title"], opportunity)
            if exc.code in {"test_required", "application_denied", "invalid_vacancy"}:
                return await self._external_action(
                    session, attempt, user, match, opportunity, source, resume["title"], exc.code
                )
            if exc.code == "auth_required":
                mark_reauth_required(connection)
                attempt.status = ApplicationAttemptStatus.FAILED
                attempt.error_code = exc.code
                attempt.detail = exc.user_message
                await record_event(
                    session, match, "hh_application_failed", actor="system", detail=exc.user_message
                )
                await session.commit()
                return ApplicationOutcome(
                    "hh",
                    "connection_required",
                    "Подключите HH снова",
                    exc.user_message,
                    opportunity.source_url,
                    resume["title"],
                    error_code=exc.code,
                )
            attempt.status = (
                ApplicationAttemptStatus.UNCERTAIN
                if exc.code == "uncertain"
                else ApplicationAttemptStatus.FAILED
            )
            attempt.error_code = exc.code
            attempt.detail = exc.user_message
            await record_event(
                session, match, "hh_application_failed", actor="system", detail=exc.user_message
            )
            await session.commit()
            return _attempt_outcome(attempt, opportunity.source_url, resume["title"])

        attempt.status = ApplicationAttemptStatus.SUBMITTED
        attempt.external_id = str(result.get("id") or "") or None
        attempt.result = {**attempt.result, "response": "accepted"}
        if match.status == OpportunityStatus.RECOMMENDED:
            await transition_application(session, match, OpportunityStatus.APPROVED, actor="hh")
        if match.status == OpportunityStatus.APPROVED:
            await transition_application(
                session, match, OpportunityStatus.CONTACTED, actor="hh", detail="HH подтвердил отклик"
            )
        await record_event(session, match, "hh_application_submitted", actor="hh")
        await session.commit()
        return _attempt_outcome(attempt, opportunity.source_url, resume["title"])

    async def _already_applied(
        self,
        session: AsyncSession,
        attempt: ApplicationAttempt,
        match: UserOpportunity,
        resume_title: str,
        opportunity: Opportunity,
    ) -> ApplicationOutcome:
        attempt.status = ApplicationAttemptStatus.ALREADY_APPLIED
        attempt.error_code = "already_applied"
        attempt.detail = ERROR_MESSAGES["already_applied"]
        if match.status == OpportunityStatus.RECOMMENDED:
            await transition_application(session, match, OpportunityStatus.APPROVED, actor="hh")
        if match.status == OpportunityStatus.APPROVED:
            await transition_application(
                session, match, OpportunityStatus.CONTACTED, actor="hh", detail="Отклик уже есть на HH"
            )
        await session.commit()
        return _attempt_outcome(attempt, opportunity.source_url, resume_title)

    async def _external_action(
        self,
        session: AsyncSession,
        attempt: ApplicationAttempt,
        user: TelegramUser,
        match: UserOpportunity,
        opportunity: Opportunity,
        source: SourceConfig,
        resume_title: str,
        reason: str,
    ) -> ApplicationOutcome:
        attempt.status = ApplicationAttemptStatus.EXTERNAL_ACTION_REQUIRED
        attempt.error_code = reason
        attempt.detail = ERROR_MESSAGES[reason]
        command = await create_application_command(
            session,
            self.settings,
            user,
            match,
            opportunity,
            f"hh-fallback:{attempt.id}",
        )
        attempt.result = {**attempt.result, "extension_command_id": str(command.id)}
        await record_event(session, match, "hh_external_action_required", actor="hh", detail=attempt.detail)
        await session.commit()
        outcome = _attempt_outcome(attempt, opportunity.source_url, resume_title)
        outcome.command = command_payload(command)
        return outcome


def _selected_resume(metadata: dict, selected_id: str | None) -> dict | None:
    if not selected_id:
        return None
    return next(
        (item for item in metadata.get("resumes", []) if str(item.get("id")) == selected_id),
        None,
    )


def _attempt_outcome(
    attempt: ApplicationAttempt, url: str | None, resume_title: str | None
) -> ApplicationOutcome:
    status = attempt.status.value
    title, message = {
        "processing": ("Отправляем отклик", "Ждём подтверждение HH."),
        "submitted": ("Отклик отправлен", "HH подтвердил отправку."),
        "already_applied": ("Отклик уже отправлен", ERROR_MESSAGES["already_applied"]),
        "external_action_required": ("Нужно действие на HH", attempt.detail or "Продолжите на HH."),
        "failed": ("Отклик не отправлен", attempt.detail or ERROR_MESSAGES["request_failed"]),
        "uncertain": ("Проверьте HH", ERROR_MESSAGES["uncertain"]),
    }[status]
    return ApplicationOutcome("hh", status, title, message, url, resume_title, error_code=attempt.error_code)
