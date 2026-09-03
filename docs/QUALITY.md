# VzyalZakaz — Quality, Refactoring and Delivery

Статус: обязательный quality contract проекта.

Этот документ отвечает за refactoring, legacy removal, testing, static checks, build, CI, release readiness и Definition of Done.

---

## 1. Основной принцип

Работа не завершена после написания кода.

Она завершена после доказательства, что:

1. новый сценарий работает;
2. старые сценарии не сломаны;
3. новая реализация не дублирует существующую;
4. заменённый код удалён;
5. repository остаётся поддерживаемым.

---

## 2. Reuse-first refactoring

Перед созданием новой реализации выполнить repository search.

Искать:

- похожие components;
- services;
- hooks;
- types;
- adapters;
- styles;
- utilities;
- endpoints.

Если решение уже есть — переиспользовать или расширить.

---

## 3. Legacy removal rule

Когда новая реализация заменяет старую:

1. мигрировать callers;
2. выполнить search старого symbol/path;
3. удалить старую реализацию;
4. удалить unused tests;
5. удалить unused style/config/types;
6. повторить static checks.

Запрещено оставлять старое «на всякий случай».

Git уже хранит историю.

---

## 4. No parallel implementations

Без документированной технической причины в кодовой базе не должны одновременно существовать:

- два API clients одной системы;
- два button systems;
- два status vocabularies;
- два ranking implementations;
- old/new frontend;
- несколько способов конфигурировать одну интеграцию.

Если transition неизбежен, migration должен иметь ясную границу и быть завершён в разумном scope.

---

## 5. Refactoring scope

Refactoring оправдан, если:

- нужен для правильной реализации;
- удаляет duplication в затронутой области;
- исправляет ownership;
- существенно упрощает дальнейшую поддержку.

Не делать unrelated rewrite.

---

## 6. Test strategy

Использовать несколько уровней тестов.

### Unit

Для:

- pure transformations;
- domain rules;
- scoring helpers;
- parsers;
- validators.

### Integration

Для:

- database behaviour;
- API + service + persistence;
- important adapters с fixture responses;
- migrations;
- background pipelines.

### Component tests

Для важного интерактивного UI:

- state changes;
- validation;
- errors;
- conditional content.

### E2E

Для основных пользовательских сценариев.

Минимально критичные сценарии:

- открыть orders;
- открыть order detail;
- reject/save/other main order action;
- подготовить application;
- approve/send;
- увидеть application state;
- connection problem/recovery;
- прямой deep link.

---

## 7. What not to test

Не создавать tests ради покрытия строки.

Избегать:

- tests implementation details;
- огромных snapshots;
- теста, что framework делает то, что framework гарантирует;
- mocks, повторяющих реализацию production code.

Test должен защищать meaningful behaviour.

---

## 8. Regression tests

Если исправляется реальный bug, сначала или одновременно создать test, который воспроизводит проблему, если это разумно.

Это особенно важно для:

- parsing;
- deduplication;
- status transitions;
- ranking;
- external adapters;
- authorization.

---

## 9. Frontend quality gate

Перед merge frontend changes должны пройти актуальные equivalent-команды проекта:

```bash
npm run lint
npm run typecheck
npm test
npm run build
```

Если отдельного `typecheck`/`test` script пока нет — его следует добавить в рамках настройки quality pipeline, а не постоянно обходить.

Для visual changes проверить mobile, tablet/desktop, browser, PWA и Telegram WebView, если relevant.

---

## 10. Backend quality gate

Целевой baseline:

```bash
ruff check .
ruff format --check .
mypy <backend-package>
pytest
```

Конкретные команды могут соответствовать текущему layout проекта.

Если часть инструментария ещё не внедрена, внедрять постепенно, но итоговый CI должен иметь:

- lint;
- format check;
- tests;
- type checking на practical strictness;
- migration validation.

---

## 11. Python standards

Рекомендуемый toolchain:

- Python 3.10 compatibility, если это текущий contract;
- `ruff` для lint + format;
- `mypy` или `pyright` для typing;
- `pytest`;
- `pytest-asyncio`, если требуется;
- `coverage` для анализа пробелов, но не как vanity target.

Не вводить Black + isort + flake8 параллельно с Ruff без необходимости.

---

## 12. TypeScript standards

Рекомендуемый baseline:

- TypeScript strict mode насколько позволяет проект;
- ESLint;
- formatter;
- framework build;
- component/E2E tests.

Не использовать массовый `eslint-disable` вместо исправления.

---

## 13. CI pipeline

Целевой pipeline pull request:

1. dependency install;
2. formatting validation;
3. lint;
4. typecheck;
5. unit tests;
6. integration tests;
7. frontend build;
8. backend migration validation;
9. extension build/typecheck, если relevant;
10. E2E critical flows;
11. optional visual regression для UI changes.

Independent jobs можно запускать параллельно.

Merge blocked при failure обязательного job.

---

## 14. Build reproducibility

Build должен быть воспроизводимым из clean checkout.

Нельзя полагаться на:

- локальный незакоммиченный файл;
- manually installed global dependency;
- secret, который не описан;
- generated file, отсутствующий в documented build process.

---

## 15. Dependency policy

Перед добавлением dependency проверить:

- нельзя ли решить уже установленным инструментом;
- maintenance status;
- package size для frontend;
- security;
- licensing;
- необходимость.

Удалять dependency после удаления последнего usage.

---

## 16. Migrations

CI должен как минимум проверять:

- migration scripts импортируются;
- metadata/schema state согласован с migration policy;
- migration chain не сломана.

Production schema никогда не меняется ручным SQL вместо versioned migration, кроме emergency procedure с последующим обязательным отражением в migration history.

---

## 17. Visual QA

Для затронутых основных экранов проверять:

- `360px`;
- `390px`;
- tablet;
- `1280px+`.

Особое внимание:

- overflow;
- sticky/footer overlap;
- long Russian text;
- empty state;
- validation errors;
- large numbers;
- slow loading.

---

## 18. Visual regression

Рекомендуется Playwright screenshot coverage для стабильных shell/pages.

Не snapshot every pixel всей системы без причины.

Лучшие кандидаты:

- app shell;
- order list;
- order detail;
- application approval;
- connection state.

---

## 19. Accessibility verification

Минимально:

- keyboard navigation;
- visible focus;
- semantic headings;
- form labels;
- icon accessible names;
- no critical information color-only.

Автоматический accessibility check рекомендуется в E2E для ключевых страниц.

---

## 20. Performance checks

Не вводить строгие vanity budgets без измерений.

Но проверять regressions:

- bundle explosion;
- repeated fetches;
- N+1 backend access;
- huge DOM lists;
- unbounded concurrency;
- repeated expensive ranking.

---

## 21. Security checks

Не коммитить secrets.

CI должен иметь secret scanning через GitHub/platform mechanisms либо эквивалент.

Dependency vulnerability alerts должны быть включены там, где доступны.

---

## 22. Pull request quality

Хороший PR:

- одна понятная задача;
- без unrelated cleanup;
- без generated noise;
- без dead code;
- с tests для changed behaviour;
- с docs update, если изменён contract.

---

## 23. Definition of Done

Любая задача считается завершённой, если:

### Code

- implementation complete;
- ownership корректен;
- duplication не добавлено;
- legacy удалён;
- naming понятен;
- no unnecessary dependency.

### Product

- user flow завершён;
- loading/error/empty предусмотрены;
- state consistent;
- failure recoverable, где возможно.

### Frontend

- responsive;
- accessible;
- design contract соблюдён;
- fake success отсутствует.

### Backend

- API/domain boundaries соблюдены;
- migrations добавлены при schema change;
- external failure behaviour определено;
- side effects safe.

### Verification

- required static checks pass;
- tests pass;
- build pass;
- critical affected flow проверен.

### Docs

- source of truth обновлён, если contract изменился.

Если что-либо не проверено, coding agent обязан явно указать это в handoff.
