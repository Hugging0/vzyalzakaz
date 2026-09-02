from __future__ import annotations

import asyncio
import html
import logging
import re
import socket
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlparse

import aiohttp
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import AppSettings, PortfolioProject
from app.models import CollectorRun, Opportunity, OpportunityStatus, TelegramUser, UserOpportunity
from app.services.application_workflow import record_event, transition_application
from app.services.content_classifier import DEMAND_CATEGORIES, is_demand_category
from app.services.portfolio_documents import extract_document_text
from app.services.recommendations import RecommendationService
from app.services.voice import VoiceTranscriber
from app.services.web_sessions import create_login_ticket
from app.telegram.ui import app_button, button

logger = logging.getLogger(__name__)
SKIP_REASONS = {
    "skill": "Не мой профиль",
    "work": "Слишком объёмно",
    "budget": "Низкий бюджет",
    "fulltime": "Нужна полная занятость",
    "client": "Не подходит заказчик",
    "interest": "Неинтересно",
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
        self._configure_task: asyncio.Task | None = None
        self._running = False
        self._client: aiohttp.ClientSession | None = None
        self._transcriber = VoiceTranscriber(settings)

    async def start(self) -> None:
        self._running = True
        timeout = aiohttp.ClientTimeout(total=50, connect=15, sock_connect=15, sock_read=45)
        connector = aiohttp.TCPConnector(family=socket.AF_INET, ttl_dns_cache=300)
        self._client = aiohttp.ClientSession(timeout=timeout, connector=connector)
        self._task = asyncio.create_task(self._poll(), name="telegram-bot-polling")
        self._configure_task = asyncio.create_task(
            self._configure(),
            name="telegram-bot-configure",
        )

    async def _configure(self) -> None:
        try:
            await self._api(
                "setMyCommands",
                {
                    "commands": [
                        {"command": "start", "description": "Открыть поиск проектов"},
                        {"command": "app", "description": "Открыть кабинет"},
                        {"command": "help", "description": "Как это работает"},
                    ]
                },
            )
            if self.settings.mini_app_url:
                await self._api(
                    "setChatMenuButton",
                    {
                        "menu_button": {
                            "type": "web_app",
                            "text": "Кабинет",
                            "web_app": {"url": self._app_url("/app/today")},
                        }
                    },
                )
        except Exception:
            logger.exception("Cannot configure Telegram bot commands; polling will still start")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        if self._configure_task:
            self._configure_task.cancel()
            await asyncio.gather(self._configure_task, return_exceptions=True)
        if self._client:
            await self._client.close()
            self._client = None

    async def notify(self, opportunity: Opportunity) -> None:
        """Fan out one global opportunity into isolated per-user recommendations."""
        if not is_demand_category(opportunity.content_category):
            return
        async with self.session_factory() as session:
            users = (
                await session.scalars(select(TelegramUser).where(TelegramUser.is_active.is_(True)))
            ).all()
            for user in users:
                notifications = (user.profile or {}).get("ui", {}).get("notifications", {})
                if notifications.get("strongMatches", True) is False:
                    continue
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
        retry_delay = 2
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
                retry_delay = 2
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Telegram bot polling failed (%s); retrying", type(exc).__name__)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 20)

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
                start_value = text.partition(" ")[2].strip()
                if start_value.startswith("web-login"):
                    await self._send_web_login_link(
                        user,
                        _web_login_destination(start_value),
                    )
                else:
                    await self._welcome(user)
                return
            if not user:
                if callback:
                    await self._answer_callback(callback["id"], "Сначала откройте бота и нажмите START")
                else:
                    await self._send_message(telegram_user_id, "Для регистрации отправьте /start")
                return

        if message:
            await self._handle_message(user, message)
        elif callback:
            await self._handle_callback(user, callback)

    async def _handle_message(self, user: TelegramUser, message: dict) -> None:
        text = (message.get("text") or "").strip()
        if text.startswith("/"):
            await self._handle_command(user, text)
            return
        if message.get("voice"):
            await self._handle_voice(user, message["voice"])
            return
        if message.get("document"):
            await self._handle_document(user, message["document"], message.get("caption", ""))
            return
        ui = (user.profile or {}).get("ui", {})
        if text and (ui.get("intake_state") == "awaiting_about" or not ui.get("onboarding_completed")):
            await self._complete_profile_from_text(user, text)
            return
        await self._send_message(
            user.telegram_user_id,
            "Выберите действие ниже. Профиль можно обновить обычным сообщением без команд.",
            self._home_keyboard(configured=True),
        )

    async def _can_register(self, session, telegram_data: dict, text: str) -> bool:
        supplied = text.partition(" ")[2].strip()
        return await self.recommendations.can_register(
            session,
            int(telegram_data["id"]),
            supplied or None,
        )

    async def _welcome(self, user: TelegramUser) -> None:
        ui = (user.profile or {}).get("ui", {})
        configured = bool(ui.get("onboarding_completed"))
        await self._send_message(
            user.telegram_user_id,
            "<b>Проекты под ваш опыт</b>\n\n"
            + (
                "Поиск настроен. Отклики остаются под вашим контролем."
                if configured
                else (
                    "Расскажите о себе одним сообщением: текстом или голосом. "
                    "Портфолио можно добавить позже."
                )
            ),
            self._home_keyboard(configured),
        )

    async def _handle_command(self, user: TelegramUser, text: str) -> None:
        command, _, value = text.partition(" ")
        command = command.lower().split("@")[0]
        value = value.strip()
        if command == "/start":
            if value.startswith("web-login"):
                await self._send_web_login_link(user, _web_login_destination(value))
            else:
                await self._welcome(user)
        elif command == "/help":
            await self._send_message(
                user.telegram_user_id,
                _help_text(),
                self._app_keyboard("Открыть кабинет"),
            )
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
            await self._update_number(user, value, "threshold", 60, 95)
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
            db_user.profile = _profile_with_ui(db_user, profile)
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
            db_user.profile = _profile_with_ui(db_user, profile)
            if field != "threshold":
                await self.recommendations.reset_recommendations(session, db_user)
            else:
                await session.commit()
        await self._send_message(user.telegram_user_id, "Настройка сохранена. Вызовите /digest.")

    async def _update_about(self, user: TelegramUser, value: str) -> None:
        if not value:
            await self._send_message(user.telegram_user_id, "Пример: <code>/about Делаю Python API...</code>")
            return
        async with self.session_factory() as session:
            db_user = await session.get(TelegramUser, user.id)
            profile = self.recommendations.profile_for(db_user)
            profile.candidate.about = value[:2000]
            db_user.profile = _profile_with_ui(db_user, profile)
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
            "Уведомления включены." if active else "Уведомления приостановлены. /resume включает их.",
        )

    async def _open_mini_app(self, user: TelegramUser) -> None:
        if not self.settings.mini_app_url:
            await self._send_message(
                user.telegram_user_id,
                "Веб-кабинет будет доступен после настройки HTTPS-домена.",
            )
            return
        await self._send_message(
            user.telegram_user_id,
            "Заказы, отклики и настройки находятся в веб-кабинете.",
            self._app_keyboard("Открыть кабинет"),
        )

    def _app_keyboard(self, label: str) -> list | None:
        if not self.settings.mini_app_url:
            return None
        return [[app_button(label, self._app_url("/app/today"))]]

    def _home_keyboard(self, configured: bool) -> list:
        rows = []
        if configured and self.settings.mini_app_url:
            rows.append([app_button("Открыть кабинет", self._app_url("/app/today"))])
            rows.append([button("Обновить профиль", callback_data="intake:start")])
        else:
            rows.append(
                [button("Рассказать о себе", callback_data="intake:start", style="primary")]
            )
            if self.settings.mini_app_url:
                rows.append([app_button("Заполнить в кабинете", self._app_url("/app/profile"))])
        return rows

    async def _complete_profile_from_text(self, user: TelegramUser, text: str) -> None:
        if len(text) < 20:
            await self._send_message(
                user.telegram_user_id,
                "Добавьте пару деталей: чем занимаетесь, какие задачи берёте и что хотели бы найти.",
            )
            return
        await self._api("sendChatAction", {"chat_id": user.telegram_user_id, "action": "typing"})
        async with self.session_factory() as session:
            db_user = await session.get(TelegramUser, user.id)
            await self.recommendations.apply_profile_intake(session, db_user, text)
        keyboard = []
        if self.settings.mini_app_url:
            keyboard.append([app_button("Смотреть заказы", self._app_url("/app/orders"))])
        keyboard.append(
            [button("Добавить портфолио", callback_data="intake:portfolio", style="success")]
        )
        await self._send_message(
            user.telegram_user_id,
            "<b>Профиль готов.</b> Я выделил навыки из рассказа и запустил подбор. "
            "Портфолио необязательно. Его можно прислать файлом сейчас или позже.",
            keyboard,
        )

    async def _handle_voice(self, user: TelegramUser, voice: dict) -> None:
        if int(voice.get("file_size") or 0) > 20 * 1024 * 1024:
            await self._send_message(user.telegram_user_id, "Голосовое длиннее 20 МБ. Пришлите короче.")
            return
        await self._api("sendChatAction", {"chat_id": user.telegram_user_id, "action": "typing"})
        path: Path | None = None
        try:
            path = await self._download_telegram_file(voice["file_id"], ".ogg")
            transcript = await self._transcriber.transcribe(path)
            if len(transcript) < 20:
                raise RuntimeError("The voice transcript is empty")
            await self._complete_profile_from_text(user, transcript)
        except Exception:
            logger.exception("Voice profile intake failed")
            await self._send_message(
                user.telegram_user_id,
                "Не удалось уверенно разобрать запись. Пришлите более короткое голосовое или текст.",
            )
        finally:
            if path:
                path.unlink(missing_ok=True)

    async def _handle_document(self, user: TelegramUser, document: dict, caption: str) -> None:
        if int(document.get("file_size") or 0) > 20 * 1024 * 1024:
            await self._send_message(user.telegram_user_id, "Файл больше 20 МБ. Пришлите облегчённую версию.")
            return
        file_name = (document.get("file_name") or "Портфолио")[:200]
        suffix = Path(file_name).suffix[:12]
        path: Path | None = None
        try:
            await self._api("sendChatAction", {"chat_id": user.telegram_user_id, "action": "typing"})
            path = await self._download_telegram_file(document["file_id"], suffix)
            extracted = await asyncio.to_thread(
                extract_document_text,
                path,
                document.get("mime_type"),
            )
            description = (caption.strip() or extracted or f"Файл портфолио: {file_name}")[:1500]
            async with self.session_factory() as session:
                db_user = await session.get(TelegramUser, user.id)
                profile = self.recommendations.profile_for(db_user)
                slug = re.sub(r"[^a-z0-9]+", "-", file_name.lower()).strip("-") or "portfolio"
                project = PortfolioProject(
                    slug=f"{slug}-{int(datetime.now(UTC).timestamp())}",
                    title=Path(file_name).stem[:200] or "Портфолио",
                    description=description,
                    skills=profile.candidate.skills[:50],
                    telegram_file_id=document["file_id"],
                    file_name=file_name,
                    mime_type=document.get("mime_type"),
                )
                db_user.portfolio = [*(db_user.portfolio or []), project.model_dump()]
                await session.commit()
            await self._send_message(
                user.telegram_user_id,
                f"<b>{html.escape(file_name)}</b> добавлен в портфолио.",
                self._app_keyboard("Открыть проекты"),
            )
        except Exception:
            logger.exception("Portfolio document intake failed")
            await self._send_message(
                user.telegram_user_id,
                "Не удалось обработать файл. Подойдут PDF, DOCX, TXT или Markdown до 20 МБ.",
            )
        finally:
            if path:
                path.unlink(missing_ok=True)

    async def _download_telegram_file(self, file_id: str, suffix: str) -> Path:
        file_info = await self._api("getFile", {"file_id": file_id})
        remote_path = file_info.get("file_path")
        if not remote_path or not self._client:
            raise RuntimeError("Telegram did not return a file path")
        url = f"https://api.telegram.org/file/bot{self.settings.telegram_bot_token}/{remote_path}"
        async with self._client.get(url) as response:
            response.raise_for_status()
            payload = await response.read()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as output:
            output.write(payload)
            return Path(output.name)

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
                        Opportunity.content_category.in_(DEMAND_CATEGORIES),
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
        if data.startswith("intake:"):
            await self._handle_intake_callback(user, callback, data.partition(":")[2])
            return
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
                        Opportunity.content_category.in_(DEMAND_CATEGORIES),
                    )
                )
            ).one_or_none()
            if not row:
                await self._answer_callback(callback["id"], "Рекомендация не найдена")
                return
            match, opportunity, db_user = row
            if action == "approve":
                proposal = await self.recommendations.generate_proposal(session, db_user, match, opportunity)
                await record_event(session, match, "proposal_ready", actor="telegram")
                await session.commit()
                keyboard = []
                if self.settings.mini_app_url:
                    keyboard.append(
                        [app_button("Проверить отклик", self._app_url(f"/app/applications/{match.id}"))]
                    )
                if opportunity.contact_username:
                    username = opportunity.contact_username.lstrip("@")
                    keyboard.append(
                        [button("Написать заказчику", url=f"https://t.me/{username}", style="primary")]
                    )
                if opportunity.source_url:
                    keyboard.append([button("Открыть источник", url=opportunity.source_url)])
                keyboard.append(
                    [
                        button(
                            "Я откликнулся",
                            callback_data=f"contacted:{match.id}",
                            style="success",
                        )
                    ]
                )
                await self._send_message(
                    user.telegram_user_id,
                    "<b>Персональный черновик для ручной проверки</b>\n\n"
                    f"<pre>{html.escape(proposal)}</pre>",
                    keyboard,
                )
                await self._answer_callback(callback["id"], "Черновик готов")
            elif action == "skip":
                keyboard = [
                    [
                        button(label, callback_data=f"reason:{match.id}:{key}")
                        for key, label in list(SKIP_REASONS.items())[index : index + 2]
                    ]
                    for index in range(0, len(SKIP_REASONS), 2)
                ]
                await self._send_message(user.telegram_user_id, "Почему пропускаем?", keyboard)
                await self._answer_callback(callback["id"], "Выберите причину")
            elif action == "reason":
                match.skip_reason = SKIP_REASONS.get(extra[0] if extra else "", "not interested")
                await transition_application(
                    session,
                    match,
                    OpportunityStatus.SKIPPED,
                    actor="telegram",
                    detail=match.skip_reason,
                )
                await self._answer_callback(callback["id"], "Сохранено")
            elif action == "details":
                await self._send_message(user.telegram_user_id, _format_details(opportunity, match))
                await self._answer_callback(callback["id"])
            elif action == "contacted":
                await transition_application(
                    session,
                    match,
                    OpportunityStatus.CONTACTED,
                    actor="telegram",
                )
                await self._answer_callback(callback["id"], "Отклик отмечен")

    async def _handle_intake_callback(
        self,
        user: TelegramUser,
        callback: dict,
        action: str,
    ) -> None:
        if action == "start":
            async with self.session_factory() as session:
                db_user = await session.get(TelegramUser, user.id)
                raw_profile = dict(db_user.profile or {})
                ui = dict(raw_profile.get("ui", {}))
                ui["intake_state"] = "awaiting_about"
                raw_profile["ui"] = ui
                db_user.profile = raw_profile
                await session.commit()
            await self._send_message(
                user.telegram_user_id,
                "<b>Расскажите о себе одним сообщением.</b>\n\n"
                "Например: чем занимаетесь, какие задачи любите, с какими инструментами работаете "
                "и какой бюджет рассматриваете. Можно написать текст или записать голосовое.",
            )
            await self._answer_callback(callback["id"])
            return
        if action == "portfolio":
            await self._send_message(
                user.telegram_user_id,
                "Пришлите PDF, DOCX, TXT или Markdown. Можно добавить короткую подпись к файлу.",
                [[button("Продолжить без файла", callback_data="intake:finish")]],
            )
            await self._answer_callback(callback["id"])
            return
        if action == "finish":
            await self._send_message(
                user.telegram_user_id,
                "Готово. Портфолио можно добавить в любой момент, просто отправив файл в этот чат.",
                self._app_keyboard("Открыть проекты"),
            )
            await self._answer_callback(callback["id"])
            return
        await self._answer_callback(callback["id"], "Действие устарело")

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
            f"Последняя ошибка: {html.escape(last_error.source)}. "
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
        keyboard = []
        first_row = []
        if self.settings.mini_app_url:
            first_row.append(
                app_button("Посмотреть", self._app_url(f"/app/orders/{match.id}"))
            )
        first_row.append(
            button(
                "Подготовить отклик",
                callback_data=f"approve:{match.id}",
                style="primary",
            )
        )
        keyboard.append(first_row)
        keyboard.append(
            [button("Не подходит", callback_data=f"skip:{match.id}", style="danger")]
        )
        await self._send_message(chat_id, _format_card(opportunity, match), keyboard)

    async def _send_web_login_link(
        self,
        user: TelegramUser,
        destination: str = "/app/today",
    ) -> None:
        origin = self._public_origin()
        if not origin:
            await self._send_message(user.telegram_user_id, "Веб-вход пока не настроен.")
            return
        async with self.session_factory() as session:
            db_user = await session.get(TelegramUser, user.id)
            ticket = await create_login_ticket(session, db_user, self.settings)
        login_url = f"{origin}/auth/telegram?ticket={ticket}&next={quote(destination, safe='')}"
        await self._send_message(
            user.telegram_user_id,
            "Ссылка действует 10 минут и откроет ваш кабинет в браузере.",
            [[button("Войти в кабинет", url=login_url, style="primary")]],
        )

    def _public_origin(self) -> str | None:
        if self.settings.public_base_url:
            return self.settings.public_base_url.rstrip("/")
        if self.settings.mini_app_url:
            parsed = urlparse(self.settings.mini_app_url)
            if parsed.scheme and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}"
        return None

    def _app_url(self, path: str) -> str:
        origin = None
        if self.settings.mini_app_url:
            parsed = urlparse(self.settings.mini_app_url)
            if parsed.scheme and parsed.netloc:
                origin = f"{parsed.scheme}://{parsed.netloc}"
        origin = origin or self._public_origin()
        return f"{origin}{path}" if origin else (self.settings.mini_app_url or path)

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
        if not self._client:
            raise RuntimeError("Telegram Bot API client is not started")

        async def request_once() -> tuple[int, dict]:
            request_timeout = aiohttp.ClientTimeout(total=timeout)
            async with self._client.post(
                f"{self.base_url}/{method}",
                json=payload,
                timeout=request_timeout,
            ) as response:
                return response.status, await response.json(content_type=None)

        for attempt in range(3):
            try:
                status, body = await request_once()
                if status == 429:
                    retry_after = body.get("parameters", {}).get("retry_after", 1)
                    await asyncio.sleep(min(int(retry_after), 10))
                    status, body = await request_once()
                if status >= 400:
                    raise RuntimeError(f"Telegram Bot API request failed for {method}: HTTP {status}")
                break
            except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
                if attempt == 2:
                    error_type = type(exc).__name__
                    raise RuntimeError(
                        f"Telegram Bot API request failed for {method}: {error_type}"
                    ) from None
                await asyncio.sleep(1 + attempt * 2)
        if not body.get("ok"):
            raise RuntimeError(body.get("description", "Telegram Bot API error"))
        return body.get("result")


def _web_login_destination(payload: str) -> str:
    value = payload.removeprefix("web-login").lstrip("-")
    static_routes = {
        "": "/app/today",
        "today": "/app/today",
        "orders": "/app/orders",
        "applications": "/app/applications",
        "portfolio": "/app/portfolio",
        "connections": "/app/connections",
        "analytics": "/app/analytics",
        "profile": "/app/profile",
        "settings": "/app/settings",
    }
    if value in static_routes:
        return static_routes[value]
    kind, _, raw_id = value.partition("-")
    if raw_id.isdigit() and int(raw_id) > 0:
        if kind == "order":
            return f"/app/orders/{raw_id}"
        if kind == "application":
            return f"/app/applications/{raw_id}"
    return "/app/today"


def _help_text() -> str:
    return (
        "<b>Как это работает</b>\n\n"
        "Расскажите о своём опыте текстом или голосом. Я соберу профиль, отберу проекты и "
        "объясню совпадения. Портфолио можно прислать файлом, но это необязательно.\n\n"
        "Отклики отправляете только вы."
    )


def _profile_with_ui(user: TelegramUser, profile) -> dict:
    raw_profile = profile.model_dump()
    raw_profile["ui"] = dict((user.profile or {}).get("ui", {}))
    return raw_profile


def _format_card(opportunity: Opportunity, match: UserOpportunity) -> str:
    budget = "не указан"
    if opportunity.budget_min or opportunity.budget_max:
        low = f"{opportunity.budget_min:,.0f}" if opportunity.budget_min else "?"
        high = f"{opportunity.budget_max:,.0f}" if opportunity.budget_max else "?"
        budget = f"{low}-{high} {opportunity.currency or ''}".strip()
    analysis = match.analysis or {}
    strength = str(analysis.get("strength_label") or "Совпадение")
    why = analysis.get("why_recommended") or []
    reason = why[0].get("text") if why and isinstance(why[0], dict) else None
    return (
        f"<b>{html.escape(strength)} · {match.final_score:.0f}/100</b>\n"
        f"{html.escape(opportunity.title[:140])}\n"
        f"{html.escape(opportunity.source)} · {html.escape(budget)}\n\n"
        f"{html.escape(str(reason or 'Откройте заказ, чтобы увидеть разбор совпадения.'))}"
    )


def _format_details(opportunity: Opportunity, match: UserOpportunity) -> str:
    analysis = match.analysis or {}
    matched = ", ".join(analysis.get("matched_capabilities") or []) or "нет прямых совпадений"
    missing = ", ".join(analysis.get("missing_must_haves") or []) or "не обнаружены"
    why = [
        item.get("text")
        for item in analysis.get("why_recommended", [])
        if isinstance(item, dict) and item.get("text")
    ]
    checks = [
        item.get("text")
        for item in analysis.get("checks", [])
        if isinstance(item, dict) and item.get("text")
    ]
    why_text = "\n".join(f"{index}. {html.escape(text)}" for index, text in enumerate(why, 1))
    checks_text = "\n".join(f"• {html.escape(text)}" for text in checks)
    return (
        f"<b>{html.escape(opportunity.title)}</b>\n\n"
        f"<b>{html.escape(str(analysis.get('strength_label') or 'Совпадение'))} · "
        f"{match.final_score:.0f}/100</b>\n\n"
        f"<b>Почему рекомендуем</b>\n{why_text or 'Нужна ручная проверка'}\n\n"
        f"<b>Навыки:</b> {html.escape(matched)}\n"
        f"<b>Что не подтверждено:</b> {html.escape(missing)}\n"
        f"<b>Кейс:</b> {html.escape(match.portfolio_item or 'не выбран')}"
        + (f"\n\n<b>Что проверить</b>\n{checks_text}" if checks_text else "")
    )
