# VzyalZakaz — Agent Handbook

Статус: обязательная точка входа для coding agents.

Цель правил — не только получить работающий код, но и не допускать постепенного ухудшения архитектуры, интерфейса и пользовательского опыта при последовательных AI-изменениях.

---

## 1. Что читать перед работой

### Всегда

1. `PRODUCT.md`
2. `docs/AGENT_HANDBOOK.md`

### UI / UX / frontend

Дополнительно:

1. `DESIGN.md`
2. `docs/FRONTEND_RULES.md`
3. `docs/QUALITY.md`

### Backend / API / workers / integrations

Дополнительно:

1. `docs/BACKEND_RULES.md`
2. `docs/QUALITY.md`

### Recommendation / ranking

Дополнительно:

- `docs/RECOMMENDATION_ARCHITECTURE.md`

### Browser extension

Дополнительно:

- `docs/BROWSER_EXTENSION_ARCHITECTURE.md`
- `docs/ADDING_EXTENSION_ADAPTER.md`

### PWA / Telegram / cross-surface behaviour

Дополнительно:

- `docs/WEB_PWA_ARCHITECTURE.md`

Не загружай в контекст документацию, не относящуюся к задаче.

---

## 2. Источники истины

Не дублировать правила между документами.

| Область | Source of truth |
|---|---|
| продукт | `PRODUCT.md` |
| UI / visual / UX | `DESIGN.md` |
| frontend engineering | `docs/FRONTEND_RULES.md` |
| backend engineering | `docs/BACKEND_RULES.md` |
| tests / refactoring / CI / DoD | `docs/QUALITY.md` |
| recommendation-specific architecture | `docs/RECOMMENDATION_ARCHITECTURE.md` |
| extension | `docs/BROWSER_EXTENSION_ARCHITECTURE.md` |
| PWA / Telegram integration | `docs/WEB_PWA_ARCHITECTURE.md` |

Если информация уже закреплена в source of truth, не копируй её в другой файл.

---

## 3. Главный engineering principle

Каждое изменение должно делать проект:

- функциональнее;
- понятнее;
- либо как минимум не увеличивать technical debt.

Работа не считается хорошей, если новая функция работает, но:

- дублирует существующий код;
- создаёт второй способ решения той же задачи;
- оставляет ненужный legacy;
- нарушает ownership;
- создаёт локальный UI-паттерн;
- создаёт дополнительный source of truth;
- усложняет следующую доработку.

Не оптимизировать исключительно под минимальный diff.

---

## 4. Обязательный workflow

### Step 1 — Inspect

Перед реализацией:

- прочитать затронутый код;
- найти related components;
- найти related hooks/services;
- найти types/schemas;
- найти API contracts;
- найти callers;
- найти tests;
- найти старые реализации;
- проверить relevant docs.

Не предполагать, что нужной абстракции нет.

Использовать repository search до создания нового component, service или utility.

### Step 2 — Understand ownership

До написания кода определить:

- где живёт источник истины;
- кто владеет состоянием;
- какой слой содержит бизнес-правило;
- что должно быть pure presentation;
- какие существующие сущности нужно переиспользовать.

Если ownership неясен — сначала исправить архитектурную границу.

### Step 3 — Reuse before create

Приоритет:

1. reuse;
2. extend;
3. refactor existing;
4. create new.

Не создавать abstraction заранее.

Но если два компонента являются разными копиями одного системного паттерна — объединить через primitive.

### Step 4 — Implement vertical slice

Пользовательская функция рассматривается целиком:

`UI → client state → API → application/domain logic → persistence/integration → response → UI state`

Не завершать работу на одном слое, если из-за этого сценарий остаётся partially implemented.

### Step 5 — Remove replaced implementation

После миграции callers удалить заменённую реализацию.

Без технически обоснованной необходимости запрещены:

- `Old*`;
- `New*`;
- `Legacy*`;
- `*V2`;
- compatibility wrapper;
- unused endpoints;
- duplicate components;
- dead feature flags;
- commented-out code;
- abandoned styles;
- unused DTO.

Git является историей. Старый код не нужно хранить внутри актуального дерева «на всякий случай».

### Step 6 — Verify

Запустить проверки из `docs/QUALITY.md`.

Кроме автоматических проверок, проверить реальный user flow.

Build success сам по себе не является доказательством правильности.

### Step 7 — Update documentation when rule changed

Документация обновляется, если изменение:

- создаёт повторяемый UI pattern;
- меняет архитектурный boundary;
- меняет status lifecycle;
- вводит новый deployment/verification requirement;
- меняет основной product behaviour.

Не создавать новый `.md`, если информация естественно помещается в существующий source of truth.

---

## 5. Работа с legacy

Legacy определяется не возрастом кода, а наличием более правильной замены.

При обнаружении legacy в области задачи:

1. найти callers;
2. определить актуальную реализацию;
3. мигрировать callers;
4. удалить legacy;
5. удалить связанные types/styles/tests/config;
6. проверить repository search.

Не оставлять unused compatibility code без причины.

---

## 6. Минимизация сложности

Не добавлять:

- dependency ради небольшой функции;
- class без состояния/ответственности;
- service только ради имени `Service`;
- repository abstraction, если storage не нуждается в границе;
- global state для локального UI;
- configuration option без реального product requirement;
- feature flag без rollout plan;
- helper, делающий код менее читаемым;
- generic component с десятками флагов.

Предпочитать ясную композицию специализированных частей.

---

## 7. Правило ответственности

Модуль должен иметь понятную причину изменения.

Если файл отвечает одновременно за transport, business rules, persistence, serialization и formatting — его следует разделить.

При этом запрещено искусственное дробление на файлы по 20 строк.

---

## 8. Naming

Названия должны отражать доменную ответственность.

Предпочитать:

- `ApplicationStatus`
- `RecommendationReason`
- `ConnectionHealth`

вместо:

- `DataManager`
- `Processor`
- `Helper`
- `Util`
- `Handler2`

`utils`, `helpers`, `common` не должны становиться свалкой.

---

## 9. Comments

Комментарий должен объяснять:

- why;
- constraint;
- non-obvious tradeoff.

Комментарий не должен переводить код на человеческий язык.

---

## 10. Error handling

Не проглатывать ошибки.

Нельзя использовать broad exception handling без необходимости.

Ошибки должны:

- сохранять context;
- быть логируемыми;
- не раскрывать sensitive data;
- преобразовываться на корректной архитектурной границе.

Frontend не должен угадывать значение backend error по текстовой строке, если можно использовать стабильный error code.

---

## 11. External integrations

Любая внешняя система считается ненадёжной.

Обязательные вопросы:

- timeout;
- retry policy;
- idempotency;
- rate limit;
- authentication expiration;
- partial response;
- schema changes;
- observability.

Adapter должен изолировать external representation от internal domain.

---

## 12. AI-specific failure modes

Перед завершением задачи проверить, не появились ли:

- duplicate implementation;
- almost-identical component;
- giant file;
- needless abstraction;
- generic manager/service;
- random config;
- duplicate DTO;
- hidden business logic in UI;
- fake success state;
- excessive defensive code;
- multiple styles for same component;
- новый documentation file без необходимости.

---

## 13. Scope discipline

Если в области задачи обнаружена небольшая очевидная проблема — исправить.

Не превращать локальную задачу в repository-wide rewrite без необходимости.

Если более крупный refactoring нужен для корректного решения, сделать его целенаправленно и завершённо.

---

## 14. Handoff after implementation

В финальном handoff coding agent должен коротко указать:

- что изменено;
- какие legacy части удалены;
- какие проверки выполнены;
- что не проверено и почему;
- есть ли migrations/config/env changes.

Не перечислять каждый изменённый файл без необходимости.
