# VzyalZakaz — Frontend Rules

Статус: обязательный engineering contract для Web/PWA frontend.

Визуальные правила находятся в `DESIGN.md`.
Product behaviour — в `PRODUCT.md`.
Testing/refactoring/CI — в `docs/QUALITY.md`.

---

## 1. Основная архитектурная идея

Frontend разделяется на:

1. routing/composition;
2. feature/domain UI;
3. shared UI primitives;
4. data access;
5. mapping;
6. shared technical utilities.

Presentation layer не должен становиться местом хранения backend/domain logic.

---

## 2. Route layer

Route/page отвечает за:

- получение route params;
- high-level composition;
- server/client boundary;
- page-level loading/error;
- подключение feature-level modules.

Route не должен содержать:

- большие domain algorithms;
- duplicate API clients;
- десятки UI primitives;
- complex mapping;
- reusable business rules.

---

## 3. Feature layer

Feature отвечает за конкретный пользовательский сценарий.

Примеры:

- order recommendation;
- application approval;
- connection recovery;
- profile skill editing.

Feature может содержать feature components, feature-specific hooks, view models и локальную orchestration.

Feature не должен копировать shared primitive.

---

## 4. Shared UI primitives

Системный component нужен, если visual/interaction pattern повторяется.

**same pattern → same primitive**

Примеры:

- button;
- field;
- card;
- notice;
- dialog;
- badge;
- toggle;
- segmented control;
- skeleton;
- page header.

Не создавать `SpecialButton`, если задачу можно решить вариантом `AppButton`.

Если API primitive стал неудобным, сначала проверить, не стал ли он слишком generic.

---

## 5. Domain components vs generic components

Предпочтительны domain components:

- `OrderRecommendationSummary`
- `ApplicationStatusPanel`
- `ConnectionHealthCard`

вместо generic:

- `InfoBox`
- `DataCard`
- `SmartPanel`

Generic primitives отвечают за внешний паттерн.
Domain components отвечают за смысл.

---

## 6. State ownership

Состояние хранится на минимально необходимом уровне.

Приоритет:

1. local component state;
2. feature state;
3. server/query cache;
4. global state только для действительно глобальной сущности.

Не помещать в global store локальные accordion/modal/field состояния.

Backend state не копировать вручную в несколько client stores.

---

## 7. Server state

Данные backend должны иметь один понятный access layer.

Запрещено:

- вызывать `fetch` хаотично из presentation components;
- иметь несколько несовместимых API clients;
- вручную дублировать caching strategy в каждой feature;
- использовать UI text как способ интерпретации backend errors.

Server state должен поддерживать loading, stale/revalidate strategy, error, mutation state и invalidation.

---

## 8. DTO → UI model

Backend transport shape не обязан совпадать с удобной UI-моделью.

Если преобразование нетривиально:

`API DTO → mapper → UI/domain view model → component`

Mapping не должен быть размазан по JSX.
Нельзя дублировать один mapper на нескольких экранах.

---

## 9. Types

Не использовать `any` как стандартный обход type system.

`unknown` предпочтительнее для непроверенных external values.

Не создавать отдельный frontend type, полностью повторяющий backend type, если его можно безопасно generated/shared.

UI-specific view models допустимы и желательны, когда presentation needs отличаются.

---

## 10. Components

Признаки необходимости refactoring:

- одновременно data fetching, mapping, mutations и большая JSX-разметка;
- множество несвязанных effects;
- десятки props;
- условные ветки, соответствующие нескольким разным продуктовым сценариям;
- сложные callback chains.

Не использовать формальный line limit как единственный критерий.

Если компонент трудно понять целиком за один проход — разделить по ответственности.

---

## 11. Hooks

Hook нужен для reusable stateful behaviour.

Не выносить каждый `useState` в custom hook.

Hook не должен скрывать непредсказуемые side effects.

Названия hooks должны отражать функцию, например `useApplicationApproval`, а не `useData`.

---

## 12. Effects

`useEffect` не является стандартным способом синхронизации всего со всем.

Перед effect проверить:

- можно ли вычислить значение во время render;
- можно ли выполнить действие в event handler;
- принадлежит ли state query/cache layer;
- можно ли решить через key/remount.

Effects должны иметь ясную external synchronization responsibility.

---

## 13. Mutations

Mutation UI обязан различать pending, success и error.

Запрещён optimistic success для действий, где ошибка существенно меняет результат, если rollback не реализован.

Особенно это касается:

- отправки отклика;
- изменения connection;
- auto-apply;
- удаления;
- действий browser extension.

---

## 14. Forms

Использовать один form pattern.

Правила:

- видимый label;
- validation schema не дублируется вручную в нескольких местах;
- submit state виден;
- recoverable backend error не очищает форму;
- double submit предотвращён.

---

## 15. Routing

Deep links должны работать независимо от Telegram runtime.

Основные routes должны корректно открываться напрямую.

UI не должен предполагать, что пользователь всегда пришёл через Today.

Detail screen должен самостоятельно получить необходимое состояние.

---

## 16. PWA / Telegram WebView

Core Web/PWA UI должен работать:

- в обычном browser;
- standalone;
- Telegram WebView.

Telegram-specific integration изолируется адаптером.

Нельзя разбрасывать проверки Telegram runtime по всему component tree.

---

## 17. Styling

Использовать design tokens из единого места.

Запрещено в feature styles:

- hardcoded brand colors;
- random radii;
- random shadows;
- локальные font scales;
- копирование стилей primitives.

Если значение системное — оно является token.

---

## 18. Iconography

Использовать единый icon set.

Нельзя импортировать альтернативную библиотеку ради одной иконки.

Icon-only control использует общий primitive.

---

## 19. Copy

Повторяемый domain text может иметь единый источник, когда это реально снижает риск расхождения.

Не превращать простые подписи в гигантскую систему constants.

Не хранить UI copy внутри backend.

---

## 20. Accessibility

Для каждого interactive component:

- keyboard;
- focus;
- semantic element;
- accessible name;
- disabled state;
- error state при необходимости.

Clickable `div` запрещён, когда нужен `button` или `a`.

---

## 21. Performance

Не оптимизировать преждевременно.

Но не допускать очевидных проблем:

- огромные dependencies;
- client-side rendering всего приложения без причины;
- повторный запрос одних данных;
- тяжёлые вычисления на каждый render;
- загрузка всего списка, если реально нужна pagination/infinite loading.

Memoization используется только при реальной необходимости.

---

## 22. Lists

Для больших order/application lists предусматривать:

- pagination или controlled incremental loading;
- стабильные keys;
- empty state;
- loading state;
- retry;
- preserving filters when returning from detail.

Пользователь не должен терять место и фильтры после просмотра заказа.

---

## 23. Tests

Минимально тестировать:

- non-trivial pure logic;
- mapping;
- critical component behaviour;
- critical workflows через E2E.

Не писать огромные snapshot tests как замену behavioural tests.

Подробнее — `docs/QUALITY.md`.

---

## 24. Frontend Definition of Done

Перед завершением UI/frontend задачи:

- использованы существующие primitives;
- новый повторяемый pattern добавлен в system, а не локально;
- нет duplicate implementation;
- mobile проверен;
- desktop проверен;
- keyboard/focus проверены;
- loading/error/empty предусмотрены;
- mutation не показывает fake success;
- deep link работает;
- tests/lint/typecheck/build прошли;
- replaced frontend legacy удалён.
