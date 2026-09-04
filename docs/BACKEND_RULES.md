# VzyalZakaz — Backend Rules

Статус: обязательный engineering contract для backend, integrations, workers и API.

Цель backend — быть надёжным источником истины для состояния поиска, рекомендаций, подключений и откликов.

---

## 1. Архитектурные слои

Backend логически разделяется на:

1. API / transport;
2. application/use cases;
3. domain rules;
4. persistence;
5. external integrations;
6. background execution;
7. infrastructure/configuration.

Физическая структура может меняться, но ответственности не должны смешиваться без причины.

---

## 2. API layer

API отвечает за:

- parsing request;
- authentication/authorization;
- transport validation;
- вызов application use case;
- mapping result to response;
- stable error response.

API endpoint не должен содержать основную бизнес-логику.

Плохо:

- ranking непосредственно внутри route;
- database orchestration на десятки строк;
- marketplace scraping logic в endpoint.

---

## 3. Application layer

Application/use-case layer координирует сценарий.

Примеры:

- approve application;
- create recommendation;
- refresh connection;
- ingest source item.

Он может вызывать domain logic, repositories, external adapters и определять transaction boundary.

Не должен зависеть от UI representation.

---

## 4. Domain rules

Бизнес-правило должно существовать в одном месте.

Примеры:

- допустимые transitions application status;
- условия auto-apply;
- recommendation semantics;
- eligibility;
- deduplication rules.

Нельзя реализовать одно правило отдельно в API, worker, extension и Telegram handler.

---

## 5. Persistence

Database — источник истины для persistent state.

Правила:

- schema changes только migrations;
- migrations versioned;
- destructive migrations требуют осознанного плана;
- application startup не должен молча «чинить» production schema;
- database models не должны бесконтрольно вытекать наружу как API contract.

---

## 6. Transactions

Transaction boundary соответствует бизнес-операции.

Избегать commit после каждого маленького repository call и длинной транзакции вокруг внешнего HTTP request.

Сначала определить, что должно быть атомарным.

---

## 7. Repositories

Repository нужен для meaningful persistence boundary.

Не создавать repository interface на каждую таблицу только ради архитектурного шаблона.

Repository не должен содержать unrelated business logic.

---

## 8. External adapters

Каждая внешняя площадка/источник изолируется adapter boundary.

Adapter отвечает за:

- external authentication;
- request/response format;
- parsing;
- mapping external identifiers;
- external-specific errors.

Внутренний domain не должен знать DOM selectors конкретного marketplace.

---

## 9. Source ingestion

Pipeline ingestion должен разделять:

1. fetch;
2. parse;
3. normalize;
4. deduplicate;
5. persist;
6. classify/rank;
7. notify/update downstream.

Не смешивать весь pipeline в одном giant function.

Каждый stage должен быть наблюдаемым.

---

## 10. Idempotency

Повторный запуск background job не должен создавать:

- duplicate order;
- duplicate application;
- duplicate notification;
- duplicate external action.

Для side effects, особенно отправки откликов, idempotency обязательна.

---

## 11. External actions

Отправка отклика или иное действие на внешней площадке должно иметь явный lifecycle.

Минимально различать:

- requested;
- processing;
- succeeded;
- failed;
- uncertain, если внешняя система не дала надёжного подтверждения.

Нельзя считать action успешным только потому, что HTTP request завершился без exception.

Способ отправки выбирается backend-реестром `ApplicationProvider`, а не условием по имени
площадки во frontend. `HHApplicationProvider` использует официальный API;
`BrowserExtensionApplicationProvider` ставит существующую `ApplicationCommand`. Один
user-facing endpoint возвращает доменное состояние, включая `external_action_required`.

Токены внешних площадок принадлежат паре user/provider, шифруются перед записью и никогда
не входят в DTO. OAuth `state` случайный, одноразовый, ограничен TTL и хранится только как hash.
Внешняя mutation без подтверждённого ответа получает `uncertain`: автоматический retry запрещён.

Для источника HH действует отдельная data boundary: исходный текст и факты не передаются во
внешний LLM. Разрешить это можно только после явного письменного согласования с HH и отдельного
изменения `HH_ALLOW_EXTERNAL_LLM`; local deterministic extraction, retrieval и proposal fallback
остаются доступны.

---

## 12. Retries

Retry допускается только для transient failures.

Использовать bounded retries, backoff и jitter при необходимости.

Не retry:

- invalid credentials;
- validation error;
- permanent permission denial;
- deterministic parser bug.

Повтор external mutation обязан быть idempotent-safe.

---

## 13. Timeouts

Любой внешний network call имеет timeout.

Бесконечное ожидание запрещено.

---

## 14. Rate limits

External integrations должны учитывать platform, Telegram, provider API и AI provider limits.

Rate limit error должен иметь controlled behaviour, а не общий crash.

---

## 15. Background jobs

Job должен:

- иметь bounded responsibility;
- логировать start/result/error;
- быть повторяемым безопасно;
- не зависеть от локальной памяти предыдущего run;
- иметь понятный ownership.

Не запускать важные production background workflows случайными fire-and-forget tasks внутри HTTP request process.

---

## 16. Queues and scheduling

Не добавлять queue infrastructure заранее.

Но если operation длительная, retryable, independent от HTTP lifecycle или требует concurrency control — её следует выполнять через подходящий background mechanism.

---

## 17. Application statuses

Statuses являются domain contract.

Transitions должны быть валидированы backend.

Frontend не определяет самостоятельно, какой переход разрешён.

Нельзя использовать произвольные strings в разных частях backend.

---

## 18. Recommendation system

Recommendation engine обязан разделять:

- candidate generation;
- feature extraction;
- ranking;
- explanation;
- persistence/versioning результата.

Score не должен терять информацию о версии algorithm/model.

Explanation должна быть основана на фактах, доступных системе.

Подробнее — `docs/RECOMMENDATION_ARCHITECTURE.md`.

---

## 19. AI providers

LLM provider оборачивается собственным boundary.

Application code не должен зависеть от vendor-specific response structure.

Хранить отдельно:

- provider;
- model;
- request purpose;
- latency;
- usage/cost при доступности;
- failure class.

Не логировать secrets или чувствительный полный prompt без необходимости.

---

## 20. Structured AI output

Если AI output участвует в program logic:

- использовать schema/structured output;
- валидировать;
- иметь fallback/error handling.

Не парсить критичный результат через fragile regex из свободного prose, если доступен structured format.

---

## 21. Auth and permissions

Каждый protected endpoint проверяет identity и resource ownership.

Нельзя полагаться на то, что frontend скрыл кнопку.

Sensitive external credentials не возвращаются frontend и не логируются.

---

## 22. Configuration

Runtime configuration читается централизованно.

Запрещено:

- `os.getenv` по всему проекту;
- silent default для critical secret;
- production behaviour, зависящее от случайного local default.

Configuration validation должна происходить при startup.

---

## 23. Error model

API использует стабильную модель ошибок.

Пользовательские/ожидаемые ошибки должны иметь machine-readable code.

Например:

- `connection_expired`
- `application_already_sent`
- `source_rate_limited`

Не заставлять frontend парсить английский error message.

---

## 24. Logging

Логи должны помогать восстановить цепочку события.

Использовать structured context:

- request/job id;
- user/account id при допустимости;
- source;
- entity id;
- operation;
- result.

Не логировать password, access token, cookie или sensitive full payload без причины.

---

## 25. Observability

Для критических потоков должна быть возможность понять:

- сколько элементов fetched;
- сколько parsed;
- сколько rejected;
- сколько duplicate;
- сколько ranked;
- сколько notifications/actions succeeded/failed;
- latency;
- external failure classes.

Не обязательно сразу внедрять тяжёлую observability platform, но код должен позволять измерение.

---

## 26. Concurrency

Асинхронность используется для concurrent I/O, а не автоматически для любого кода.

Не блокировать event loop синхронным network/disk operation.

При параллельной обработке:

- ограничивать concurrency;
- учитывать rate limits;
- корректно собирать partial failures.

---

## 27. Tests

Backend tests должны покрывать:

- domain rules;
- important use cases;
- adapter normalization/parsing;
- API contract;
- migrations/integration для критичных частей.

Не мокать весь мир так, что настоящая интеграция между слоями никогда не проверяется.

---

## 28. Backend Definition of Done

Перед завершением backend-задачи:

- бизнес-логика не спрятана в route;
- external-specific logic находится в adapter;
- schema change имеет migration;
- side effects idempotent;
- timeout/retry рассмотрены;
- errors имеют стабильный contract;
- logs не содержат secrets;
- replaced legacy удалён;
- automated checks пройдены;
- affected critical workflow протестирован.
