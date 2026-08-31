from __future__ import annotations

import asyncio
import html
import logging
import re
import socket
from datetime import UTC, datetime

import aiohttp
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import AppSettings, PortfolioProject
from app.models import CollectorRun, Opportunity, OpportunityStatus, TelegramUser, UserOpportunity
from app.services.recommendations import RecommendationService

logger = logging.getLogger(__name__)
SKIP_REASONS = {
    "skill": "irrelevant skill",
    "work": "too much work",
    "budget": "budget too low",
    "fulltime": "full-time",
    "client": "bad client",
    "interest": "not interested",
}


class TelegramBot:
    def __init__(
        self,
        settings: AppSettings,
        session_factory: async_sessionmaker,
        recommendations: RecommendationService,
    ):
        self.settings = settings
        self.session_factory = session_factory
        self.recommendations = recommendations
        self.base_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}"
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        try:
            await self._api(
                "setMyCommands",
                {
                    "commands": [
                        {"command": "start", "description": "Начать работу"},
                        {"command": "app", "description": "Открыть Hunt Agent"},
                        {"command": "pause", "description": "Поставить агента на паузу"},
                        {"command": "resume", "description": "Продолжить поиск"},
                        {"command": "settings", "description": "Настройки поиска"},
                        {"command": "help", "description": "Помощь"},
                    ]
                },
            )
            if self.settings.mini_app_url:
                await self._api(
                    "setChatMenuButton",
                    {
                        "menu_button": {
                            "type": "web_app",
                            "text": "Открыть Hunt Agent",
                            "web_app": {"url": self.settings.mini_app_url},
                        }
                    },
                )
        except Exception:
            logger.exception("Cannot configure Telegram bot commands; polling will still start")
        self._task = asyncio.create_task(self._poll(), name="telegram-bot-polling")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def notify(self, opportunity: Opportunity) -> None:
        """Fan out one global opportunity into isolated per-user recommendations."""
        async with self.session_factory() as session:
            users = (
                await session.scalars(select(TelegramUser).where(TelegramUser.is_active.is_(True)))
            ).all()
            for user in users:
                match = await self.recommendations.ensure_match(session, user, opportunity)
                if not match or match.notified_at:
                    continue
                profile = self.recommendations.profile_for(user)
                if match.final_score < profile.ranking.realtime_threshold:
                    continue
                await self._send_card(user.telegram_user_id, opportunity, match)
                match.notified_at = datetime.now(UTC)
                await session.commit()

    async def _poll(self) -> None:
        offset = 0
        while self._running:
            try:
                result = await self._api(
                    "getUpdates",
                    {"offset": offset, "timeout": 30, "allowed_updates": ["message", "callback_query"]},
                    timeout=40,
                )
                for update in result:
                    offset = max(offset, update["update_id"] + 1)
                    await self._handle_update(update)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Telegram bot polling failed")
                await asyncio.sleep(3)

    async def _handle_update(self, update: dict) -> None:
        callback = update.get("callback_query")
        message = update.get("message")
        telegram_data = (callback or message or {}).get("from") or {}
        telegram_user_id = telegram_data.get("id")
        if not telegram_user_id:
            return
        if message and (message.get("chat") or {}).get("type") != "private":
            return

        async with self.session_factory() as session:
            user = await self.recommendations.get_user(session, int(telegram_user_id))
            text = message.get("text", "") if message else ""
            incoming_command = text.split(maxsplit=1)[0].lower().split("@")[0] if text else ""
            if not user and incoming_command == "/start":
                if not await self._can_register(session, telegram_data, text):
                    await self._send_message(
                        telegram_user_id,
                        "Регистрация закрыта или нужен корректный invite-код: <code>/start КОД</code>",
                    )
                    return
                user = await self.recommendations.register_user(session, telegram_data)
                await self._welcome(user)
                return
            if not user:
                if callback:
                    await self._answer_callback(callback["id"], "Сначала откройте бота и нажмите START")
                else:
                    await self._send_message(telegram_user_id, "Для регистрации отправьте /start")
                return

        if message:
            await self._handle_command(user, text)
        elif callback:
            await self._handle_callback(user, callback)

    async def _can_register(self, session, telegram_data: dict, text: str) -> bool:
        if int(telegram_data["id"]) == self.settings.telegram_owner_id:
            return True
        count = await session.scalar(select(func.count()).select_from(TelegramUser)) or 0
        if count >= self.settings.max_users:
            return False
        if self.settings.registration_mode == "open":
            return True
        if self.settings.registration_mode == "closed":
            return False
        supplied = text.partition(" ")[2].strip()
        return bool(
            self.settings.registration_invite_code and supplied == self.settings.registration_invite_code
        )

    async def _welcome(self, user: TelegramUser) -> None:
        await self._send_message(
            user.telegram_user_id,
            "<b>Профиль создан.</b> Я использовал безопасные стартовые настройки.\n\n"
            "Теперь у каждого пользователя свои фильтры, оценки, статусы и отклики. "
            "Начните с /profile, затем задайте навыки командой:\n"
            "<code>/skills Python, FastAPI, PostgreSQL, AI Agents</code>\n\n"
            "После настройки вызовите /digest.",
        )

    async def _handle_command(self, user: TelegramUser, text: str) -> None:
        command, _, value = text.partition(" ")
        command = command.lower().split("@")[0]
        value = value.strip()
        if command in {"/start", "/help"}:
            await self._send_message(user.telegram_user_id, _help_text())
        elif command == "/app":
            await self._open_mini_app(user)
        elif command == "/settings":
            await self._send_message(user.telegram_user_id, self._profile_text(user))
        elif command == "/profile":
            await self._send_message(user.telegram_user_id, self._profile_text(user))
        elif command == "/skills":
            await self._update_list(user, value, "skills")
        elif command == "/languages":
            await self._update_list(user, value, "languages")
        elif command == "/hours":
            await self._update_number(user, value, "hours", 1, 80)
        elif command == "/rate":
            await self._update_number(user, value, "rate", 0, 1_000_000)
        elif command == "/threshold":
            await self._update_number(user, value, "threshold", 0, 100)
        elif command == "/about":
            await self._update_about(user, value)
        elif command == "/portfolio":
            await self._add_portfolio(user, value)
        elif command == "/portfolio_clear":
            await self._clear_portfolio(user)
        elif command == "/pause":
            await self._set_active(user, False)
        elif command == "/resume":
            await self._set_active(user, True)
        elif command == "/stats":
            await self._send_message(user.telegram_user_id, await self._stats_text(user))
        elif command == "/admin" and user.is_admin:
            await self._send_message(user.telegram_user_id, await self._admin_text())
        elif command == "/digest":
            await self._digest(user)
        else:
            await self._send_message(user.telegram_user_id, "Неизвестная команда. Используйте /help")

    async def _update_list(self, user: TelegramUser, value: str, field: str) -> None:
        values = list(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))
        if not values:
            example = "Python, FastAPI, Docker" if field == "skills" else "ru, en"
            await self._send_message(user.telegram_user_id, f"Пример: <code>/{field} {example}</code>")
            return
        async with self.session_factory() as session:
            db_user = await session.get(TelegramUser, user.id)
            profile = self.recommendations.profile_for(db_user)
            if field == "skills":
                profile.candidate.skills = values[:100]
            else:
                profile.candidate.languages = values[:10]
            db_user.profile = profile.model_dump()
            await self.recommendations.reset_recommendations(session, db_user)
        await self._send_message(
            user.telegram_user_id, "Настройка сохранена. Вызовите /digest для пересчёта."
        )

    async def _update_number(
        self, user: TelegramUser, value: str, field: str, minimum: int, maximum: int
    ) -> None:
        try:
            number = int(value)
            if not minimum <= number <= maximum:
                raise ValueError
        except ValueError:
            await self._send_message(user.telegram_user_id, f"Укажите целое число от {minimum} до {maximum}.")
            return
        async with self.session_factory() as session:
            db_user = await session.get(TelegramUser, user.id)
            profile = self.recommendations.profile_for(db_user)
            if field == "hours":
                profile.availability.max_hours_week = number
            elif field == "rate":
                profile.economics.target_hourly_rub = number
            else:
                profile.ranking.realtime_threshold = number
                profile.ranking.digest_threshold = min(profile.ranking.digest_threshold, number)
            db_user.profile = profile.model_dump()
            await self.recommendations.reset_recommendations(session, db_user)
        await self._send_message(user.telegram_user_id, "Настройка сохранена. Вызовите /digest.")

    async def _update_about(self, user: TelegramUser, value: str) -> None:
        if not value:
            await self._send_message(user.telegram_user_id, "Пример: <code>/about Делаю Python API...</code>")
            return
        async with self.session_factory() as session:
            db_user = await session.get(TelegramUser, user.id)
            profile = self.recommendations.profile_for(db_user)
            profile.candidate.about = value[:2000]
            db_user.profile = profile.model_dump()
            await session.commit()
        await self._send_message(user.telegram_user_id, "Описание сохранено.")

    async def _add_portfolio(self, user: TelegramUser, value: str) -> None:
        parts = [part.strip() for part in value.split("|")]
        if len(parts) != 3 or not all(parts):
            await self._send_message(
                user.telegram_user_id,
                "Формат: <code>/portfolio Название | Краткое описание | Python, API, Telegram</code>",
            )
            return
        title, description, raw_skills = parts
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or f"case-{user.id}"
        project = PortfolioProject(
            slug=f"{slug}-{int(datetime.now(UTC).timestamp())}",
            title=title[:200],
            description=description[:1500],
            skills=[skill.strip() for skill in raw_skills.split(",") if skill.strip()][:50],
        )
        async with self.session_factory() as session:
            db_user = await session.get(TelegramUser, user.id)
            db_user.portfolio = [*(db_user.portfolio or []), project.model_dump()]
            await session.commit()
        await self._send_message(user.telegram_user_id, "Кейс добавлен в портфолио.")

    async def _clear_portfolio(self, user: TelegramUser) -> None:
        async with self.session_factory() as session:
            db_user = await session.get(TelegramUser, user.id)
            db_user.portfolio = []
            await session.commit()
        await self._send_message(user.telegram_user_id, "Портфолио очищено.")

    async def _set_active(self, user: TelegramUser, active: bool) -> None:
        async with self.session_factory() as session:
            db_user = await session.get(TelegramUser, user.id)
            db_user.is_active = active
            await session.commit()
        await self._send_message(
            user.telegram_user_id,
            "Уведомления включены." if active else "Уведомления приостановлены. /resume — включить.",
        )

    async def _open_mini_app(self, user: TelegramUser) -> None:
        if not self.settings.mini_app_url:
            await self._send_message(
                user.telegram_user_id,
                "Mini App будет подключён после настройки HTTPS-домена. Пока используйте команды бота.",
            )
            return
        await self._send_message(
            user.telegram_user_id,
            "Откройте кабинет Hunt Agent:",
            [[{"text": "Открыть Hunt Agent", "web_app": {"url": self.settings.mini_app_url}}]],
        )

    async def _digest(self, user: TelegramUser) -> None:
        async with self.session_factory() as session:
            db_user = await session.get(TelegramUser, user.id)
            await self.recommendations.backfill_user(session, db_user)
            rows = (
                await session.execute(
                    select(UserOpportunity, Opportunity)
                    .join(Opportunity, Opportunity.id == UserOpportunity.opportunity_id)
                    .where(
                        UserOpportunity.user_id == user.id,
                        UserOpportunity.status == OpportunityStatus.RECOMMENDED,
                    )
                    .order_by(UserOpportunity.final_score.desc())
                    .limit(10)
                )
            ).all()
        if not rows:
            await self._send_message(user.telegram_user_id, "Подходящих рекомендаций пока нет.")
            return
        for match, opportunity in rows:
            await self._send_card(user.telegram_user_id, opportunity, match)

    async def _handle_callback(self, user: TelegramUser, callback: dict) -> None:
        data = callback.get("data", "")
        try:
            action, raw_id, *extra = data.split(":")
            match_id = int(raw_id)
        except (ValueError, TypeError):
            await self._answer_callback(callback["id"], "Некорректная команда")
            return
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(UserOpportunity, Opportunity, TelegramUser)
                    .join(Opportunity, Opportunity.id == UserOpportunity.opportunity_id)
                    .join(TelegramUser, TelegramUser.id == UserOpportunity.user_id)
                    .where(
                        UserOpportunity.id == match_id,
                        TelegramUser.telegram_user_id == user.telegram_user_id,
                    )
                )
            ).one_or_none()
            if not row:
                await self._answer_callback(callback["id"], "Рекомендация не найдена")
                return
            match, opportunity, db_user = row
            if action == "approve":
                proposal = await self.recommendations.generate_proposal(session, db_user, match, opportunity)
                keyboard = []
                if opportunity.contact_username:
                    username = opportunity.contact_username.lstrip("@")
                    keyboard.append([{"text": "✉️ НАПИСАТЬ В TELEGRAM", "url": f"https://t.me/{username}"}])
                if opportunity.source_url:
                    keyboard.append([{"text": "👀 ОТКРЫТЬ ВАКАНСИЮ", "url": opportunity.source_url}])
                keyboard.append([{"text": "✅ Я ОТКЛИКНУЛСЯ", "callback_data": f"contacted:{match.id}"}])
                await self._send_message(
                    user.telegram_user_id,
                    "<b>Персональный черновик — проверьте и отправьте вручную</b>\n\n"
                    f"<pre>{html.escape(proposal)}</pre>",
                    keyboard,
                )
                await self._answer_callback(callback["id"], "Черновик готов")
            elif action == "skip":
                keyboard = [
                    [
                        {"text": label, "callback_data": f"reason:{match.id}:{key}"}
                        for key, label in list(SKIP_REASONS.items())[index : index + 2]
                    ]
                    for index in range(0, len(SKIP_REASONS), 2)
                ]
                await self._send_message(user.telegram_user_id, "Почему пропускаем?", keyboard)
                await self._answer_callback(callback["id"], "Выберите причину")
            elif action == "reason":
                match.status = OpportunityStatus.SKIPPED
                match.skip_reason = SKIP_REASONS.get(extra[0] if extra else "", "not interested")
                await session.commit()
                await self._answer_callback(callback["id"], "Сохранено")
            elif action == "details":
                await self._send_message(user.telegram_user_id, _format_details(opportunity, match))
                await self._answer_callback(callback["id"])
            elif action == "contacted":
                if match.status != OpportunityStatus.APPROVED:
                    await self._answer_callback(callback["id"], "Сначала создайте черновик")
                    return
                match.status = OpportunityStatus.CONTACTED
                match.contacted_at = datetime.now(UTC)
                await session.commit()
                await self._answer_callback(callback["id"], "Отклик отмечен")

    async def _stats_text(self, user: TelegramUser) -> str:
        async with self.session_factory() as session:
            rows = (
                await session.execute(
                    select(UserOpportunity.status, func.count())
                    .where(UserOpportunity.user_id == user.id)
                    .group_by(UserOpportunity.status)
                )
            ).all()
            scanned = await session.scalar(select(func.count()).select_from(Opportunity)) or 0
        counts = {status: count for status, count in rows}
        return (
            "<b>Ваша воронка</b>\n"
            f"Просканировано общим collector: {scanned}\n"
            f"Подобрано: {sum(counts.values())}\n"
            f"Рекомендовано: {counts.get(OpportunityStatus.RECOMMENDED, 0)}\n"
            f"Одобрено: {counts.get(OpportunityStatus.APPROVED, 0)}\n"
            f"Отклик отправлен: {counts.get(OpportunityStatus.CONTACTED, 0)}\n"
            f"Ответили: {counts.get(OpportunityStatus.REPLIED, 0)}\n"
            f"Интервью: {counts.get(OpportunityStatus.INTERVIEW, 0)}\n"
            f"Выиграно: {counts.get(OpportunityStatus.WON, 0)}"
        )

    async def _admin_text(self) -> str:
        async with self.session_factory() as session:
            users = await session.scalar(select(func.count()).select_from(TelegramUser)) or 0
            active = (
                await session.scalar(
                    select(func.count()).select_from(TelegramUser).where(TelegramUser.is_active.is_(True))
                )
                or 0
            )
            matches = await session.scalar(select(func.count()).select_from(UserOpportunity)) or 0
            opportunities = await session.scalar(select(func.count()).select_from(Opportunity)) or 0
            last_error = await session.scalar(
                select(CollectorRun)
                .where(CollectorRun.error.is_not(None))
                .order_by(CollectorRun.started_at.desc())
                .limit(1)
            )
        error_text = (
            f"Последняя ошибка: {html.escape(last_error.source)} — "
            f"{html.escape((last_error.error or '')[:300])}"
            if last_error
            else "Ошибок collector пока нет"
        )
        return (
            "<b>Состояние сервиса</b>\n"
            f"Пользователи: {users} ({active} active)\n"
            f"Вакансии: {opportunities}\n"
            f"Персональные matches: {matches}\n"
            f"{error_text}"
        )

    def _profile_text(self, user: TelegramUser) -> str:
        profile = self.recommendations.profile_for(user)
        return (
            "<b>Ваш профиль</b>\n"
            f"Имя: {html.escape(profile.candidate.name)}\n"
            f"Навыки: {html.escape(', '.join(profile.candidate.skills))}\n"
            f"Языки: {html.escape(', '.join(profile.candidate.languages))}\n"
            f"До {profile.availability.max_hours_week} ч/неделю\n"
            f"Целевая ставка: {profile.economics.target_hourly_rub} ₽/ч\n"
            f"Realtime-порог: {profile.ranking.realtime_threshold:g}\n"
            f"Portfolio cases: {len(user.portfolio or [])}\n"
            f"Уведомления: {'включены' if user.is_active else 'приостановлены'}"
        )

    async def _send_card(self, chat_id: int, opportunity: Opportunity, match: UserOpportunity) -> None:
        keyboard = [
            [
                {"text": "✅ APPROVE", "callback_data": f"approve:{match.id}"},
                {"text": "❌ SKIP", "callback_data": f"skip:{match.id}"},
            ]
        ]
        second_row = [{"text": "🧠 DETAILS", "callback_data": f"details:{match.id}"}]
        if opportunity.source_url:
            second_row.insert(0, {"text": "👀 OPEN", "url": opportunity.source_url})
        keyboard.append(second_row)
        await self._send_message(chat_id, _format_card(opportunity, match), keyboard)

    async def _send_message(self, chat_id: int, text: str, keyboard: list | None = None) -> dict:
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if keyboard:
            payload["reply_markup"] = {"inline_keyboard": keyboard}
        return await self._api("sendMessage", payload)

    async def _answer_callback(self, callback_id: str, text: str | None = None) -> None:
        payload = {"callback_query_id": callback_id}
        if text:
            payload["text"] = text
        await self._api("answerCallbackQuery", payload)

    async def _api(self, method: str, payload: dict, timeout: int = 20):
        async def request_once(client: aiohttp.ClientSession) -> tuple[int, dict]:
            async with client.post(f"{self.base_url}/{method}", json=payload) as response:
                return response.status, await response.json(content_type=None)

        try:
            client_timeout = aiohttp.ClientTimeout(total=timeout)
            connector = aiohttp.TCPConnector(family=socket.AF_INET)
            async with aiohttp.ClientSession(timeout=client_timeout, connector=connector) as client:
                status, body = await request_once(client)
                if status == 429:
                    retry_after = body.get("parameters", {}).get("retry_after", 1)
                    await asyncio.sleep(min(int(retry_after), 10))
                    status, body = await request_once(client)
                if status >= 400:
                    raise RuntimeError(f"Telegram Bot API request failed for {method}: HTTP {status}")
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            error_type = type(exc).__name__
            raise RuntimeError(f"Telegram Bot API request failed for {method}: {error_type}") from None
        if not body.get("ok"):
            raise RuntimeError(body.get("description", "Telegram Bot API error"))
        return body.get("result")


def _help_text() -> str:
    return (
        "<b>Hunt Agent</b>\n\n"
        "/app — открыть кабинет\n"
        "/pause и /resume — остановить или продолжить агента\n"
        "/settings — текущие настройки поиска\n\n"
        "Новые сильные совпадения приходят сюда. По умолчанию агент готовит черновик и ждёт вашего решения."
    )


def _format_card(opportunity: Opportunity, match: UserOpportunity) -> str:
    budget = "не указан"
    if opportunity.budget_min or opportunity.budget_max:
        low = f"{opportunity.budget_min:,.0f}" if opportunity.budget_min else "?"
        high = f"{opportunity.budget_max:,.0f}" if opportunity.budget_max else "?"
        budget = f"{low}–{high} {opportunity.currency or ''}".strip()
    effort = f"~{match.estimated_effort_hours:g} ч" if match.estimated_effort_hours else "нужна оценка"
    hourly = (
        f"~{match.estimated_effective_hourly_rate:,.0f} ₽/ч"
        if match.estimated_effective_hourly_rate
        else "не рассчитано"
    )
    analysis = match.analysis or {}
    risks = analysis.get("risks") or []
    risks_text = "\n".join(f"• {html.escape(str(risk))}" for risk in risks[:4]) or "• явных рисков не найдено"
    return (
        f"🔥 <b>{match.final_score:.0f}/100 — {html.escape(opportunity.title[:120])}</b>\n"
        f"💰 {html.escape(budget)}\n⏱ {effort}\n💵 {hourly}\n"
        f"Источник: {html.escape(opportunity.source)}\n\n"
        f"FIT <b>{match.fit_score:.0f}</b> · MONEY <b>{match.money_score:.0f}</b> · "
        f"WIN <b>{match.win_score:.0f}</b>\n\n"
        f"<b>Почему подходит</b>\n"
        f"{html.escape(str(analysis.get('fit_reason') or 'Нужна ручная проверка'))}\n\n"
        f"<b>Риски</b>\n{risks_text}"
    )


def _format_details(opportunity: Opportunity, match: UserOpportunity) -> str:
    analysis = match.analysis or {}
    required = ", ".join(analysis.get("required_skills") or []) or "не определены"
    missing = ", ".join(analysis.get("missing_skills") or []) or "не определены"
    summary = str(analysis.get("summary") or opportunity.description[:1200])
    return (
        f"<b>{html.escape(opportunity.title)}</b>\n\n"
        f"{html.escape(summary[:1600])}\n\n"
        f"<b>Нужные навыки:</b> {html.escape(required)}\n"
        f"<b>Пробелы:</b> {html.escape(missing)}\n"
        f"<b>Portfolio:</b> {html.escape(match.portfolio_item or 'не выбран')}"
    )
