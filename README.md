# Personal AI JobHunter

Self-hosted агент, который собирает вакансии и проектные задачи, отбрасывает шум,
оценивает FIT / MONEY / WIN, присылает лучшие варианты в Telegram и готовит
персональный отклик только после ручного подтверждения.

Сервис поддерживает несколько пользователей. Responsive Web/PWA — основной кабинет,
Telegram-бот отвечает за срочные уведомления, быстрые действия и deep links.
Каждый пользователь получает изолированные данные.

## Что уже входит в V1

- Telethon/MTProto: realtime-сообщения, изменения и первоначальный backfill из 33 каналов;
- 16 включённых web/API/RSS-источников; всего в реестре 186 источников с явным
  статусом и режимом подключения;
- PostgreSQL + SQLAlchemy 2 + Alembic;
- exact- и content-дедупликация с сохранением всех источников репоста;
- быстрый rule-based prefilter на русском, английском и фарси;
- structured LLM-анализ через DeepSeek или OpenRouter с безопасным локальным fallback;
- FIT / MONEY / WIN / freshness и настраиваемый итоговый рейтинг;
- Telegram-карточки с цветными inline-кнопками, быстрым черновиком, отказом и deep links;
- подбор portfolio-case и генерация персонального proposal;
- отдельные данные и статусы для каждого Telegram user id;
- регистрация open/invite/closed, лимит пользователей и pause/resume;
- responsive Web/PWA на Next.js: Today, заказы, отклики, портфолио, площадки,
  статистика, профиль и настройки агента;
- собственная HttpOnly web session; Telegram `initData` и одноразовая ссылка из бота
  используются как безопасные способы bootstrap-входа;
- manifest, installable standalone shell и ограниченный offline fallback без кэша API;
- Chromium Browser Extension: безопасное подключение к PWA, очередь команд и assisted-заполнение форм Freelancer, Freelance.ru, FL.ru и Kwork без автоматического Submit;
- Nginx reverse proxy: единый адрес для Web/PWA и API;
- тестовый checkout ЮKassa с idempotency, webhook-проверкой и ручным refresh статуса;
- `APPROVE` создаёт черновик и открывает контакт — отправка остаётся ручной;
- аналитика через `/stats` в боте и `GET /api/analytics`;
- Docker Compose и тесты.

Новые биржи добавляются отдельными adapter-модулями расширения. Массовая отправка и
автоматический Submit намеренно не поддерживаются.

## Быстрый запуск

Требуется Docker Desktop / Docker Engine с Compose.

```bash
cp .env.example .env
```

Заполните как минимум Telegram-параметры в `.env` (описаны ниже). Для первого
запуска можно оставить `LLM_PROVIDER=disabled`: система будет работать с локальной
эвристикой без внешних расходов.

Авторизуйте пользовательскую Telegram-сессию интерактивно:

```bash
docker compose run --rm jobhunter python -m app.telegram_auth
```

Сессия сохранится в Docker volume `telegram_data` и не попадёт в Git.

После этого запустите сервис:

```bash
docker compose up -d --build
docker compose logs -f jobhunter
```

Проверка:

```bash
curl http://localhost:8010/api/health
```

`JOBHUNTER_PORT` оставляет FastAPI доступным только на loopback. `HTTP_PORT`
управляет публичным HTTP-входом Nginx; локально можно задать, например, `8010`.

Swagger (локально): [http://localhost:8010/docs](http://localhost:8010/docs).

## Web/PWA и вход

После запуска кабинет доступен по `http://localhost:${HTTP_PORT}/app`. Корневой
маршрут ведёт на `/app/today`; каждый заказ и отклик имеет собственный URL.

В обычном браузере `/login` открывает Telegram-бота. Бот присылает одноразовую
ссылку, после обмена которой браузер получает HttpOnly cookie. В Telegram webview
сохраняется bootstrap через проверенный `initData`, после чего также создаётся
обычная web session. Интерфейс не зависит от наличия Telegram WebApp runtime.

Telegram требует HTTPS URL для `web_app`-кнопок. После настройки домена укажите
`PUBLIC_BASE_URL=https://...` и `MINI_APP_URL=https://.../app`, выпустите TLS и
перезапустите сервис. Menu button и уведомления будут вести сразу в нужные PWA routes.

`ALLOW_DEV_AUTH=true` разрешает browser-preview с тестовым пользователем. Это
исключительно локальная настройка; на VPS её нужно оставить `false`.

## Telegram credentials

### Пользовательский аккаунт для чтения каналов

Bot API не может читать чужие каналы, поэтому collector использует ваш обычный
Telegram account через MTProto.

1. Откройте [my.telegram.org](https://my.telegram.org).
2. Войдите по номеру телефона и откройте `API development tools`.
3. Создайте приложение и сохраните `api_id` и `api_hash`.
4. Заполните в `.env`:

```dotenv
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=...
TELEGRAM_PHONE=+79990000000
```

Если VPS не может напрямую подключиться к production MTProto DC, можно направить
только пользовательский Telethon-клиент через приватный SOCKS5:

```dotenv
TELEGRAM_PROXY_HOST=proxy.example.com
TELEGRAM_PROXY_PORT=1080
TELEGRAM_PROXY_USERNAME=
TELEGRAM_PROXY_PASSWORD=
```

Прокси без логина допустим только при firewall/IP allowlist для production VPS.
Bot API, Web/PWA, база и LLM через этот прокси не маршрутизируются. Не используйте
бесплатные публичные прокси и Telegram test DC: тестовая среда не содержит production-каналы.

5. Запустите одноразовую команду авторизации из раздела выше. Если включена 2FA,
   команда отдельно запросит пароль; он не сохраняется приложением.

Аккаунт должен иметь доступ к каналам из `config/sources.yaml`. Недоступные или
несуществующие каналы будут пропущены с записью в лог, не останавливая сервис.
Стартовый backfill ограничен последними 30 сообщениями Tier A, 15 сообщениями
Tier B и 10 сообщениями Tier C; значения редактируются через `backfill_limit`.

### Бот для уведомлений

1. Создайте бота через `@BotFather` и получите token.
2. Напишите боту любое сообщение.
3. Узнайте свой numeric user id через `@userinfobot` — он нужен только для admin-default.
4. Настройте бота и регистрацию:

```dotenv
TELEGRAM_BOT_TOKEN=123456:...
TELEGRAM_OWNER_ID=123456789
REGISTRATION_MODE=invite
REGISTRATION_INVITE_CODE=длинный-случайный-код
MAX_USERS=100
```

В режиме `open` любой человек, нашедший бота, может зарегистрироваться через `/start`.
В режиме `invite` используется `/start КОД`. Режим `closed` запрещает новые регистрации,
кроме `TELEGRAM_OWNER_ID`. Existing users продолжают работать при смене режима.

У каждого пользователя собственные JSON-профиль и portfolio, а также отдельные
FIT/MONEY/WIN, статусы, причины Skip и proposal. Callback всегда проверяется против
Telegram user id, поэтому доступ к чужой рекомендации по подменённому ID запрещён.

## LLM

Без ключа система использует детерминированный scorer. Для DeepSeek:

```dotenv
LLM_PROVIDER=deepseek
LLM_API_KEY=...
LLM_MODEL=deepseek-chat
```

Для OpenRouter:

```dotenv
LLM_PROVIDER=openrouter
LLM_API_KEY=...
LLM_MODEL=deepseek/deepseek-chat
```

`LLM_BASE_URL` обычно оставляют пустым. Ответ модели валидируется строгой Pydantic
схемой. При timeout, невалидном JSON или ошибке API конкретная вакансия получает
локальную оценку, а pipeline продолжает работу.

## Источники для digital-специалистов

Помимо developer-каналов конфигурация включает review-only Telegram-источники:
`@vacancysmm`, `@vakanser_digital_smm`, `@designodromo`, `@motionhunter`,
`@cgfreelance` и `@frilans`. Они покрывают SMM, контент, дизайн, video editing,
motion, CG и широкий фриланс. Перед включением MTProto collector должен иметь
доступ к каждому каналу; недоступный канал не останавливает сервис.

Для международных remote-проектов добавлены категории Design, Marketing и Writing
из Remotive, Design и Sales/Marketing RSS из We Work Remotely, а также Jobicy
для Marketing, Design & Multimedia и Copywriting. Новые источники опрашиваются
не чаще четырёх раз в сутки, а API-выдача ограничена 30 лидами за проход, чтобы
не расходовать бюджет на анализ шума.

## Тестовая оплата ЮKassa

Checkout запускается в разделе «Профиль» Web/PWA. Все запросы идут только с
backend: frontend получает исключительно URL подтверждения. Для локального теста
заполните `.env`:

```dotenv
PUBLIC_BASE_URL=http://localhost:8010
YOOKASSA_SHOP_ID=...
YOOKASSA_SECRET_KEY=...
BILLING_PRO_MONTHLY_PRICE_RUB=990.00
```

После возврата из ЮKassa Web/PWA запрашивает статус повторно. Webhook
`POST /api/webhooks/yookassa` дополнительно сверяет платёж через API ЮKassa,
а не доверяет входящему JSON. Для production достаточно подставить production
credentials, production HTTPS `PUBLIC_BASE_URL`, назначить webhook в кабинете
ЮKassa и определить реальные тарифы.

## Настройка пользователей через Telegram

После `/start` основной сценарий — кнопки и обычный рассказ о себе. Команды не
являются основным UI; для совместимости остаются:

```text
/app
/settings
/pause
/resume
```

Владелец из `TELEGRAM_OWNER_ID` также получает `/admin` со счётчиками пользователей,
персональных matches и последней ошибкой collector.

Новые обычные пользователи начинают с пустых skills и portfolio, поэтому ваши
персональные данные им не копируются. Пользователь с `TELEGRAM_OWNER_ID` получает
стартовые значения из `candidate_profile.yaml` и `portfolio.yaml`.

## Общая настройка сервиса

Исходный код менять не нужно:

- `config/candidate_profile.yaml` — навыки, языки, доступность, экономика, веса и пороги;
- `config/portfolio.yaml` — реальные portfolio-cases. Замените примеры своими и добавьте URL;
- `config/sources.yaml` — каналы, источники, интервалы, приоритет и режим отклика.

Для временного отключения источника установите `enabled: false` и перезапустите
контейнер. Tier A/B/C сейчас выражен через `poll_interval`; Telegram работает по событиям.
HH.ru adapter включён в код, но в стартовом конфиге отключён: API HH.ru не отвечает
из текущей сети. Когда `curl https://api.hh.ru/vacancies` начнёт отвечать, поменяйте
для `hh_ru` значение на `enabled: true`.

## Политика откликов

- Telegram: после APPROVE бот показывает черновик и кнопку перехода к явно указанному контакту.
- Job boards / marketplaces: черновик и ссылка на страницу отклика.
- CAPTCHA, authentication и anti-bot protection приложение не обходит.
- Общий MTProto account используется только для чтения каналов. Он никогда не
  отправляет сообщения от имени пользователей сервиса.

## Web/PWA API

Основные маршруты:

- `GET /api/health`;
- `GET /api/opportunities?status=recommended&minimum_score=70`;
- `GET /api/opportunities/{id}`;
- `PATCH /api/opportunities/{id}/status`;
- `GET /api/analytics`;
- `POST /api/collect/{source_name}` — ручной запуск web collector.

Маршруты кабинета:

- `POST /api/web/auth/bootstrap|exchange|logout` — web session;
- `GET|PATCH /api/app/me` — профиль и настройки;
- `GET /api/app/leads` и `GET /api/app/leads/{id}` — список и detail;
- `POST|PATCH /api/app/leads/{id}/proposal` — общий backend-процесс отклика;
- `PATCH /api/app/leads/{id}/status` и `GET .../events` — воронка и история;
- `GET /api/app/sources` — connection status и capabilities;
- `/api/app/portfolio`, `/api/app/analytics`, `/api/app/billing`.
- `/api/app/extension/*` — link-ticket, состояние и отключение расширения;
- `/api/app/leads/{id}/application-command` — постановка и чтение команды отклика;
- `/api/extension/*` — собственная token-сессия, heartbeat, команды и безопасная диагностика расширения.

Внешний Nginx проксирует `/api/mini-app/*`, `/api/web/*` и `/api/app/*` вместе с PWA.
Защищённые маршруты принимают HttpOnly web session или короткую legacy-сессию во
время bootstrap. Legacy API привязан только к `127.0.0.1`.

## Подготовка к VPS

1. Используйте отдельный Linux VPS, Docker Compose и закрытый firewall.
2. Замените `POSTGRES_PASSWORD`, синхронно обновив пароль внутри `DATABASE_URL`.
3. Установите `REGISTRATION_MODE=invite` и длинный случайный invite-код.
4. Оставьте `WEB_CONCURRENCY=1`: один Bot API long-polling consumer на один token.
5. Авторизуйте общий read-only Telegram collector командой `telegram_auth`.
6. Резервно копируйте volume PostgreSQL и volume `telegram_data`.
7. Не публикуйте `JOBHUNTER_PORT`; наружу нужен только `HTTP_PORT` (80/443 через Nginx).
8. До подключения домена оставьте `MINI_APP_URL` пустым и `ALLOW_DEV_AUTH=false`.
9. Направьте A-записи `vzyalzakaz.ru`, `www.vzyalzakaz.ru` и `tg.vzyalzakaz.ru`
   на VPS, выпустите единый TLS-сертификат, задайте
   `PUBLIC_BASE_URL=https://vzyalzakaz.ru` и
   `MINI_APP_URL=https://vzyalzakaz.ru/app`, затем обновите menu button в BotFather.
10. Установите `ops/systemd/vzyalzakaz-cert-renew.*` и включите timer для
    автоматического продления сертификата. Скрипт продления использует ACME
    webroot volume и после успешной проверки перезагружает Nginx.

При последующем горизонтальном масштабировании bot polling и collectors нужно
вынести в отдельный worker с distributed lock. Текущая конфигурация рассчитана
на один VPS-процесс и PostgreSQL, но не привязана к одному конечному пользователю.

## Локальная разработка и тесты

Python 3.12+:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
DATABASE_URL=sqlite+aiosqlite:///./data/jobhunter.db pytest
ruff check .
uvicorn app.main:app --reload
```

Для локального SQLite создайте каталог `data`. Production-конфигурация использует PostgreSQL.

Browser Extension:

```bash
cd extension
npm install
cp .env.example .env
npm test
npm run typecheck
npm run build
```

Распакованная сборка находится в `extension/.output/chrome-mv3`. Для локальной
проверки откройте `chrome://extensions`, включите режим разработчика и выберите
«Загрузить распакованное расширение». Полная схема, ограничения и выпуск описаны в
`docs/BROWSER_EXTENSION_ARCHITECTURE.md`.

## Безопасность

`.env`, `*.session` и `data/` находятся в `.gitignore`. Telegram credentials не
передаются LLM. В LLM уходит только текст конкретной вакансии, профиль навыков и
выбранный portfolio-case; Telegram API secrets туда не включаются.

Перед публичным коммерческим запуском дополнительно потребуются privacy policy,
команда удаления аккаунта/экспорт данных, usage quotas, мониторинг расходов LLM,
админ-инструменты и аудит условий использования каждого источника.
