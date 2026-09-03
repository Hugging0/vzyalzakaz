# GPT-5.6 Sol handoff: ВзялЗаказ

Актуально: 2 сентября 2026 года.

> Перед любым frontend, Telegram UI или UX-copy изменением полностью читать `PRODUCT.md`, `DESIGN.md` и `docs/FRONTEND_RULES.md`. Colorblock Studio — обязательный контракт; одноразовые UI-блоки и текст меньше 13px запрещены.

## 1. Продуктовая модель

ВзялЗаказ — multi-user hunt-agent для русскоязычных фрилансеров и digital-специалистов.

- Web/PWA — основной кабинет и управление.
- Telegram Bot — сильные уведомления, быстрые решения и deep links.
- Browser Extension — следующий этап для assisted-откликов на площадках без API.
- Backend/AI — единые сбор, matching, генерация отклика, статусы и guardrails.

Полная граница поверхностей, routes, сессии и extension readiness описаны в `docs/WEB_PWA_ARCHITECTURE.md`.

## 2. Состояние репозитория и production

| Область | Состояние |
|---|---|
| Git | `main`, remote `git@github.com:Hugging0/vzyalzakaz.git`; каждую завершённую задачу тестировать, коммитить и push. |
| Production | `https://vzyalzakaz.ru/app`, Docker Compose + Nginx TLS. `/` временно отвечает `302` на `/app`; `www` и прежний `tg` канонически ведут на корневой домен. |
| Backend | FastAPI, SQLAlchemy async, PostgreSQL, Alembic. |
| Frontend | Next.js 16, React 19, TanStack Query, responsive Web/PWA. |
| Bot | Bot API long polling, цветные inline-кнопки через единый builder. |
| Collector | 49 включённых источников: 33 Telegram + 16 Web/API/RSS. Реестр содержит 186 записей. |
| MTProto | Production user session хранится только в Docker volume; Telegram traffic идёт через приватный SOCKS5. |
| Billing | ЮKassa сохранена в тестовом виде. |

Секреты, `.env`, Telegram session, базы и production credentials никогда не включать в Git или handoff.

## 3. Что реализовано в Web/PWA sprint

### Frontend

- route-first кабинет: Today, Orders, Applications, Portfolio, Connections, Analytics, Profile, Agent Settings;
- отдельные detail routes заказов и откликов;
- desktop sidebar, компактная tablet-навигация, mobile masthead и bottom navigation;
- единый Colorblock Studio CSS без градиентов, glass, glow и микрошрифта;
- новые общие primitives: `AppLinkButton`, `AppPageHeader`, `AppStat`, `AppToggle`;
- PWA manifest, install icons, standalone display, service worker и offline shell;
- Telegram WebApp script загружается только внутри `/app`, а не глобально;
- старый tab-state Mini App shell и дублирующие feature-карточки удалены.

### Авторизация

- legacy `initData` bootstrap сохранён для Telegram webview;
- `WebLoginTicket` — одноразовая ссылка из бота, token хранится как SHA-256 hash;
- `WebSession` — собственная HttpOnly/SameSite cookie с хэшированным opaque token;
- direct browser login работает через `/login` и бот;
- компактный start payload сохраняет destination для заказа, отклика или раздела;
- logout удаляет серверную сессию и cookie.

### Backend domain

- `ApplicationEvent` хранит общую историю действий Web и Telegram;
- допустимые переходы статусов собраны в `app/services/application_workflow.py`;
- `contacted` запрещён без текста отклика;
- API получил detail, filters, status transition, events, portfolio CRUD, sources/capabilities и расширенную аналитику;
- пользовательские excluded keywords и preferred sources участвуют в matching;
- глобальный ingestion не получает профиль пользователя и хранит `OpportunityFacts`; персональные `UserMatchAnalysis`, feature vector и объяснение хранятся только в `UserOpportunity`;
- UI не вычисляет возможности площадки по её имени.

### Telegram

- menu button ведёт на `/app/today`;
- уведомление содержит «Посмотреть», «Подготовить отклик», «Не подходит»;
- «Посмотреть» открывает `/app/orders/{id}`;
- готовый черновик открывается через `/app/applications/{id}`;
- обычный браузер получает одноразовую ссылку с сохранением исходного route;
- profile onboarding остаётся одним текстом/голосом, документы портфолио необязательны.

## 4. Route и API contract

Основные Web routes:

```text
/app/today
/app/orders
/app/orders/{id}
/app/applications
/app/applications/{id}
/app/portfolio
/app/connections
/app/analytics
/app/profile
/app/settings
/app/actions/{id}
```

Session API:

```text
POST /api/mini-app/auth
POST /api/mini-app/auth/dev        # только local dev
POST /api/web/auth/bootstrap
POST /api/web/auth/exchange
POST /api/web/auth/logout
```

Cabinet API:

```text
GET|PATCH /api/app/me
POST      /api/app/onboarding
GET       /api/app/leads
GET       /api/app/leads/{id}
GET       /api/app/leads/{id}/events
POST|PATCH /api/app/leads/{id}/proposal
POST      /api/app/leads/{id}/skip
POST      /api/app/leads/{id}/contacted
PATCH     /api/app/leads/{id}/status
GET       /api/app/sources
GET|POST|PATCH|DELETE /api/app/portfolio...
GET       /api/app/analytics
GET|POST  /api/app/billing...
```

Все owned-resource endpoints проверяют `UserOpportunity.user_id`; frontend не передаёт доверенный Telegram user id.

## 5. Источники и Browser Extension

Source of truth: `config/sources.yaml` и `SourceConfig`.

```text
submission_type = manual | api | browser_extension
capabilities = collect | quick_apply | browser_autofill | attachments | custom_questions | requires_auth | requires_confirmation
```

В Chromium extension реализованы адаптеры `Freelancer`, `Freelance.ru`, `FL.ru` и `Kwork`. Их selectors изолированы в adapter layer; автоматический Submit отсутствует. Сбор заказов с отключённых источников по-прежнему запрещено включать до отдельной проверки collectors.

Реализованный extension flow:

1. отдельная локальная extension auth/session;
2. fetch принадлежащего пользователю job URL и готового текста;
3. site adapters и selectors внутри extension;
4. автозаполнение в существующей browser session;
5. обязательная остановка перед Submit;
6. запись результата в `ApplicationEvent`.

Cookies и passwords площадок не отправлять backend. Не обходить CAPTCHA, robots, rate limits и source ToS.

## 6. Миграции и конфигурация

Актуальные migrations: `0005_web_sessions`, `0006_content_classification`, `0007_browser_extension`, `0008_hybrid_recommendations`, `0009_semantic_retrieval`.

Создаёт:

- `application_events`;
- `web_login_tickets`;
- `web_sessions`.
- `extension_link_tickets`, `extension_installations`;
- `application_commands`, `extension_diagnostics`.
- `opportunities.facts`, `facts_version`, `semantic_representations` и explainable matching-поля `user_opportunities`.

Полный pipeline и границы глобального/персонального анализа описаны в `docs/RECOMMENDATION_ARCHITECTURE.md`.

Контейнер backend запускает `alembic upgrade head` перед Uvicorn. Перед production deployment всё равно сделать backup PostgreSQL и проверить migration log.

Новые безопасные env names:

```dotenv
WEB_LOGIN_TICKET_TTL_SECONDS=600
WEB_SESSION_TTL_SECONDS=2592000
WEB_SESSION_COOKIE_NAME=vzyalzakaz_session
TELEGRAM_BOT_USERNAME=vzyal_zakaz_bot
```

Production использует `PUBLIC_BASE_URL=https://vzyalzakaz.ru` и `MINI_APP_URL=https://vzyalzakaz.ru/app`. Cookie автоматически получает `Secure`, когда любой из этих публичных адресов использует `https://`.

## 7. Проверки и незавершённое

Автоматические проверки sprint:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check app tests migrations
cd frontend && npm run typecheck
cd frontend && npm run lint
cd frontend && npm run build
```

Владелец явно попросил не выполнять visual QA и самостоятельно проверить графику уже на production. Поэтому после публикации остаются его проверки:

- desktop, tablet, mobile `360px`;
- standalone install/open;
- длинные названия и большие тексты;
- empty/error/loading states;
- Telegram iOS/Android webview;
- реальные deep links из production-бота.

Замечания владельца исправить отдельным focused commit. Не выдавать отсутствие screenshot QA за подтверждение визуальной готовности.

## 8. Production deployment

Только для уже pushed commit:

1. backup PostgreSQL;
2. получить commit на VPS без ручного копирования файлов;
3. `docker compose -f compose.yaml -f compose.production.yaml up -d --build`;
4. проверить migration `0005_web_sessions`, `/api/health`, frontend и container logs;
5. в обычном браузере пройти одноразовый вход через бота;
6. проверить order/application deep link и изменение статуса;
7. проверить, что collector и bot продолжают работать;
8. создать и push annotated tag `prod-YYYYMMDD-HHMM-web-pwa`.

Git rollback не откатывает migration, data, `.env`, Nginx и SOCKS5. Эти внешние изменения всегда фиксировать отдельно.

### Домен и TLS

- основной origin: `https://vzyalzakaz.ru`;
- PWA: `https://vzyalzakaz.ru/app`;
- `/` использует временный `302` на `/app`, чтобы позднее без закэшированного permanent redirect поставить SEO-страницу;
- сертификат Let’s Encrypt `vzyalzakaz.ru` включает SAN для `www.vzyalzakaz.ru` и `tg.vzyalzakaz.ru`;
- `ops/certbot-renew.sh` продлевает основной сертификат и перезагружает Nginx;
- systemd timer из `ops/systemd/` запускает проверку продления дважды в сутки;
- production dump хранится вне Git в `/opt/hunt-agent-backups` с правами `600`.

## 9. Важные файлы

```text
PRODUCT.md
DESIGN.md
docs/FRONTEND_RULES.md
docs/WEB_PWA_ARCHITECTURE.md
docs/BROWSER_EXTENSION_ARCHITECTURE.md
docs/ADDING_EXTENSION_ADAPTER.md
docs/GIT_WORKFLOW.md
docs/SOURCES_STATUS.md
docs/ROADMAP.md
app/mini_app_api.py
app/mini_app_auth.py
app/services/application_workflow.py
app/services/web_sessions.py
app/telegram/bot.py
app/telegram/ui.py
frontend/src/app/
frontend/src/components/ui/
frontend/src/components/layout/WorkspaceGate.tsx
frontend/src/components/layout/WorkspaceShell.tsx
config/sources.yaml
migrations/versions/0005_web_sessions.py
migrations/versions/0007_browser_extension.py
extension/
```
