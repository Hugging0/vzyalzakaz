# Web/PWA architecture

Статус: целевая продуктовая архитектура с 2026-09-01. Визуальный контракт находится в `DESIGN.md`, продуктовый — в `PRODUCT.md`.

## Границы интерфейсов

| Поверхность | Ответственность |
|---|---|
| Web/PWA | Основной кабинет, навигация, поиск, отклики, профиль, портфолио, площадки, статистика и настройки агента. |
| Telegram Bot | Сильные новые заказы, быстрые решения, подтверждения и deep links. Не дублирует кабинет. |
| Browser Extension | Использует локальную браузерную сессию площадки, заполняет известные поля и останавливается перед Submit. |
| Backend/AI | Единые matching, статусы, генерация отклика, правила источников и журнал событий для всех интерфейсов. |

## Маршруты

| Route | Назначение |
|---|---|
| `/app/today` | Состояние агента, итоги проверки, действия и shortlist. |
| `/app/orders` | Список заказов и фильтры. |
| `/app/orders/{id}` | Заказ, причины совпадения, источник и подготовка отклика. |
| `/app/applications` | Воронка откликов. |
| `/app/applications/{id}` | Текст, фактический статус и история событий. |
| `/app/portfolio` | Кейсы, навыки и ссылки. |
| `/app/connections` | Источники, состояние и capabilities. |
| `/app/analytics` | Воронка, response rate, источники и экономия времени. |
| `/app/profile` | Исходный рассказ, опыт, навыки, ставка и тестовый billing. |
| `/app/settings` | Порог, предпочтения, исключения, уведомления и уровень автоматизации. |
| `/app/actions/{id}` | Контекст действия, требующего подтверждения. |

Все detail routes открываются напрямую. Telegram-кнопки используют те же URL, поэтому отдельное состояние Mini App не требуется.

## Авторизация и сессии

1. В Telegram webview frontend может получить `initData` и обменять его через существующий `POST /api/mini-app/auth`.
2. `POST /api/web/auth/bootstrap` превращает короткую legacy-сессию в opaque web session.
3. В обычном браузере `/login` открывает `TELEGRAM_BOT_USERNAME` с компактным start payload. Бот создаёт одноразовый ticket на 10 минут.
4. `/auth/telegram` обменивает ticket через `POST /api/web/auth/exchange` и получает `HttpOnly`, `SameSite=Lax` cookie.
5. Ticket хранится только в хэшированном виде и используется один раз. Web session также хранится как SHA-256 hash; исходный token доступен только cookie клиента.
6. Destination кодируется ограниченным набором известных routes и после входа возвращает пользователя в исходный контекст.

Telegram остаётся bootstrap identity provider, но UI runtime от Telegram WebApp не зависит. Bot token, MTProto credentials и Telegram user id не принимаются от frontend как доверенные данные.

## Application workflow

Статусы изменяются через `app/services/application_workflow.py`. Web и Telegram вызывают одну функцию перехода и пишут `ApplicationEvent`.

```text
recommended -> approved -> contacted -> replied -> interview -> won
      |             |           |          |          -> lost
      -> skipped    -> skipped  -> lost    -> won/lost
```

`contacted` невозможен без сохранённого отклика. UI показывает завершённое действие только после успешного ответа API. Ручные callback-сценарии Telegram не должны менять статус в обход workflow.

## Источники и отправка отклика

`SourceConfig` является source of truth:

- `submission_type`: `manual`, `api`, `browser_extension`;
- `application_provider`: серверный provider официального API или browser extension;
- `capabilities`: `collect`, `quick_apply`, `browser_autofill`, `attachments`, `custom_questions`, `requires_auth`, `requires_confirmation`;
- `adapter_id` и `application_hosts`: идентификатор адаптера и строгий allowlist доменов;
- `apply_mode`: существующее серверное ограничение отправки.

`GET /api/app/sources` отдаёт нормализованные capabilities и connection status. UI только отображает контракт и не определяет возможности по имени площадки. `GET|POST /api/app/leads/{id}/application` одинаково обслуживает официальный HH API, расширение и ручной fallback. HH OAuth и выбор резюме живут в `/api/app/connections/hh/*`; токены не входят ни в один frontend payload.

Extension соблюдает границы:

- cookies и пароли площадки остаются в браузере пользователя;
- backend выдаёт команду только для принадлежащего пользователю заказа и готового текста;
- adapter площадки открывает job URL и заполняет известные поля;
- первая версия не нажимает финальный Submit;
- результат и ошибка возвращаются в общий `ApplicationEvent`;
- selectors и adapters живут в extension, а не в Web UI.

Основной HH flow: пользователь подключает аккаунт через OAuth, выбирает резюме, проверяет
сопроводительное письмо и явно нажимает «Откликнуться». Backend проверяет предыдущий отклик,
вакансию, выбранное резюме и обязательный тест. Только подтверждение HH переводит запись в
`contacted`. Тест, анкета или недоступный API-отклик создают `external_action_required` и
передают подготовку существующему расширению; финальный Submit остаётся ручным.

Одноразовый link-ticket связывает уже авторизованный PWA с отдельной сессией расширения. Токены и link codes хранятся на сервере только как SHA-256 hashes. Команды имеют idempotency key, TTL, владельца и строгий lifecycle. Service worker отправляет heartbeat и забирает задачу каждые 30 секунд через `chrome.alarms`; PWA дополнительно может разбудить установленное расширение после постановки команды. Подробный контракт находится в `docs/BROWSER_EXTENSION_ARCHITECTURE.md`.

## PWA

- Next.js manifest доступен как `/manifest.webmanifest`;
- `display: standalone`, брендовые icons и theme colors зафиксированы;
- service worker кэширует только shell/offline fallback и не делает приложение offline-first;
- API-запросы и персональные данные не кэшируются service worker;
- safe-area insets учтены для mobile masthead и нижней навигации;
- navigation/back основаны на routes, а не локальном tab state.

## Проверки

Обязательные автоматические проверки: Python tests, Ruff, TypeScript, ESLint и production build. Визуальная проверка desktop/tablet/mobile, длинных названий, больших текстов и Telegram webview обычно входит в Definition of Done. Для этой миграции владелец явно взял visual QA на себя; найденные расхождения исправляются отдельным проходом до production deployment.
