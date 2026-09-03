# VzyalZakaz Documentation Map

Документация проекта намеренно ограничена небольшим количеством sources of truth.

Не создавать новый документ, пока информация может жить в одном из существующих.

---

## Core documents

### `PRODUCT.md`

Читайте для вопросов:

- кто пользователь;
- какую проблему решаем;
- какие сценарии являются главными;
- что считается продуктовой ценностью;
- какие функции не соответствуют scope.

### `DESIGN.md`

Читайте перед любым UI/UX изменением.

Содержит:

- visual language;
- colors;
- typography;
- spacing;
- icons;
- components;
- responsive behaviour;
- recommendation UX;
- accessibility;
- content rules.

### `docs/AGENT_HANDBOOK.md`

Точка входа coding agent.

Содержит:

- порядок работы;
- правила reuse;
- ownership;
- legacy removal;
- scope discipline;
- AI-specific anti-patterns.

### `docs/FRONTEND_RULES.md`

Engineering contract Web/PWA frontend.

Содержит:

- layers;
- component responsibilities;
- state ownership;
- server data;
- mapping;
- hooks/effects;
- styling;
- routing;
- frontend DoD.

### `docs/BACKEND_RULES.md`

Engineering contract backend.

Содержит:

- API/application/domain boundaries;
- persistence;
- integrations;
- jobs;
- retries/timeouts/idempotency;
- AI providers;
- errors/logging;
- backend DoD.

### `docs/QUALITY.md`

Общий quality gate.

Содержит:

- refactoring;
- tests;
- CI;
- build;
- migrations;
- visual QA;
- Definition of Done.

---

## Specialized architecture documents

Эти документы нужны только для специфических подсистем и не должны повторять глобальные правила.

### `docs/RECOMMENDATION_ARCHITECTURE.md`

Только:

- candidate generation;
- feature model;
- ranking;
- explanation provenance;
- algorithm/model versioning.

### `docs/BROWSER_EXTENSION_ARCHITECTURE.md`

Только:

- extension runtime;
- site adapters;
- permissions;
- communication with backend;
- extension safety/fallback behaviour.

### `docs/ADDING_EXTENSION_ADAPTER.md`

Практический guide для добавления новой площадки.

### `docs/WEB_PWA_ARCHITECTURE.md`

Только cross-surface concerns:

- Web/PWA runtime;
- Telegram WebView integration;
- deep links;
- notifications;
- shared backend state.

### `docs/SOURCES_STATUS.md`

Инвентаризация источников.

Этот файл не является архитектурным контрактом.

---

## Что не создавать отдельными документами

Без особой необходимости не нужны:

- ADR directory;
- отдельный naming guide;
- отдельный refactoring guide;
- отдельный test guide;
- отдельный CI guide;
- отдельный accessibility guide;
- отдельный icon guide;
- отдельный spacing guide.

Эти правила уже имеют свой source of truth.

---

## Когда обновлять docs

Обновлять документацию в том же изменении, если:

- появилось повторяемое правило;
- изменён domain lifecycle;
- изменился visual contract;
- изменился архитектурный boundary;
- изменился required quality gate.

Документация не должна описывать систему, которой больше нет.
