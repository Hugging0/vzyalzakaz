# VzyalZakaz — Design & UX Contract

Статус: обязательный визуальный и UX-контракт для Web/PWA, Telegram-сценариев и browser extension.

Этот документ определяет единый пользовательский язык продукта. Любой повторяемый UI-паттерн обязан соответствовать этому контракту.

VzyalZakaz — рабочий инструмент для людей, которые ежедневно просматривают большое количество возможностей и принимают быстрые решения. Интерфейс должен выглядеть характерно и запоминаемо, но никогда не мешать чтению, сравнению и действию.

---

## 1. Design character

Основные характеристики:

- рабочий;
- собранный;
- быстрый;
- визуально характерный;
- не корпоративно-стерильный;
- не похожий на типичный AI dashboard;
- не игровой;
- не перегруженный.

Визуальное направление: **Colorblock Studio adapted for professional workflow**.

Бренд может быть выразительным, но рабочие поверхности должны быть спокойнее маркетинговых.

---

## 2. Главный UX-принцип

### Decision-first UI

Основная задача интерфейса — сократить время от появления возможности до осознанного действия.

При проектировании каждого экрана сначала определить:

1. Что пользователь хочет понять?
2. Какое решение он должен принять?
3. Какое главное действие следует после решения?
4. Какие данные обязательны до этого действия?

Только после этого строится композиция экрана.

---

## 3. Visual hierarchy

Использовать четыре уровня:

1. Page
2. Section
3. Entity / card
4. Metadata

Не создавать дополнительный визуальный уровень без необходимости.

На одном viewport не должно одновременно конкурировать более 1–2 сильных акцентов.

---

## 4. Цветовая система

### Base

| Token | Value | Purpose |
|---|---|---|
| `bg-canvas` | `#F6F3EC` | основной фон |
| `bg-surface` | `#FFFDFA` | карточки, формы |
| `ink-primary` | `#17223D` | основной текст и контуры |
| `ink-muted` | `#5C6475` | вторичный текст |
| `border-strong` | `#17223D` | брендовые контуры |
| `border-soft` | `#D8D6CF` | тихие разделители |

### Brand

| Token | Value |
|---|---|
| `brand-primary` | `#ED4569` |
| `brand-soft` | `#F58AA2` |

Brand pink используется для:

- primary CTA;
- brand identity;
- selected accents.

Он **не используется как semantic success** и не должен автоматически означать высокий ranking.

### Semantic

| Meaning | Token | Value |
|---|---|---|
| info | `semantic-info` | `#DFE7FF` |
| success | `semantic-success` | `#DCEADF` |
| attention | `semantic-warning` | `#F4E3A6` |
| danger | `semantic-danger` | `#B82643` |
| danger soft | `semantic-danger-soft` | `#F8D9DF` |

Цвет статуса должен иметь одинаковое значение во всём приложении.

### Запрещено

- красить каждую карточку в отдельный яркий цвет;
- использовать brand pink как статус качества;
- создавать новые semantic colors в feature CSS;
- использовать градиенты;
- glow;
- glassmorphism;
- размытые декоративные тени.

---

## 5. Surfaces and borders

Брендовые карточки:

- border: `2px solid var(--ink-primary)`;
- hard shadow: `3px 3px 0 var(--ink-primary)`;
- базовый radius: `18px 6px 18px 6px`.

Controls:

- radius: `10px 4px 10px 4px`;
- button hard shadow: максимум `2px 2px 0`.

Не каждая рабочая поверхность обязана иметь hard shadow.

Для плотных списков допускаются более спокойные flat rows с мягкими разделителями.

**Чем выше информационная плотность, тем спокойнее должен быть контейнер.**

---

## 6. Typography

Основной шрифт:

`Golos Text, system-ui, sans-serif`

Display / короткие характерные заголовки:

`Unbounded, Golos Text, sans-serif`

Unbounded не используется для длинных текстов, form labels, таблиц и metadata.

| Role | Size / Line |
|---|---|
| display | `32/36` |
| page title | `28/32` |
| section title | `20/26` |
| card title | `17/22` |
| body | `16/24` |
| button | `15/20` |
| metadata | `14/20` |
| small | `13/18` |

Меньше `13px` запрещено.
Body text меньше `15px` на mobile запрещён.
Не использовать uppercase для длинных label.

---

## 7. Spacing

Использовать ограниченную шкалу:

`4, 8, 12, 16, 20, 24, 32, 40, 48`

Предпочтения:

- page horizontal mobile: `16px`;
- tablet: `24px`;
- desktop content gutter: `28–32px`;
- card padding: `16–20px`;
- section gap: `24–32px`;
- плотные list rows: `12–16px`.

Не вводить случайные значения без причины.

---

## 8. Layout

### Mobile до `680px`

- одна колонка;
- bottom navigation;
- основные действия reach-friendly;
- detail screens отдельными routes;
- sticky CTA разрешён для ключевого действия;
- горизонтальный scroll запрещён, кроме специально предназначенных списков.

### Tablet `681–1087px`

- compact sidebar или rail;
- основное содержимое не растягивать на всю ширину;
- detail может переходить в двухколоночный layout, если это улучшает сравнение.

### Desktop от `1088px`

- постоянный sidebar;
- основная рабочая область использует доступную ширину;
- list/detail pattern предпочтителен там, где пользователь часто сравнивает сущности;
- не помещать mobile card stack в огромный desktop canvas.

Оптимальная ширина prose/content: примерно `720–860px`.
Рабочие таблицы и списки могут быть шире.

---

## 9. Navigation

Главные sections:

- Today;
- Orders;
- Applications;
- Portfolio;
- Connections;
- Analytics;
- Profile;
- Settings.

Mobile navigation показывает наиболее частые разделы + `Ещё`.

Не добавлять отдельный top-level route, если функция логически принадлежит существующему разделу.

---

## 10. Icons

Использовать один icon set во всём frontend, предпочтительно текущий выбранный системный набор или Lucide.

Правила:

- stroke icons;
- стандартный размер `20px`;
- metadata icon `16–18px`;
- standalone interactive target минимум `44px`;
- каждая icon-only button имеет `aria-label`;
- emoji не являются системными иконками;
- sparkle/magic-wand не используется как универсальная метафора AI.

Нельзя смешивать несколько библиотек иконок без технической причины.

---

## 11. Buttons

Основные варианты:

- `primary`;
- `secondary`;
- `ghost`;
- `success`;
- `danger`.

Минимальная высота:

- mobile: `46px`;
- desktop compact contexts: не менее `40px`.

Primary button на экране обычно один.

Название кнопки описывает действие:

- `Подготовить отклик`
- `Отправить`
- `Подтвердить`
- `Открыть проект`
- `Не подходит`

Избегать абстрактных `ОК`, `Да`, `Запустить`, если действие можно назвать точнее.

---

## 12. Forms

Каждое поле содержит:

- видимый label;
- control;
- optional hint;
- error state.

Placeholder не заменяет label.
Validation errors показываются рядом с полем.
Форма не должна стирать введённые данные после recoverable error.
Primary submit не меняет состояние интерфейса на success до подтверждения backend.

---

## 13. Cards and lists

Карточка существует только если у сущности есть собственная визуальная граница.

Для длинных рабочих списков предпочтительнее rows/list items, а не десятки тяжёлых цветных карточек.

Карточка заказа в списке должна позволять быстро увидеть:

- title;
- budget;
- source;
- recency;
- recommendation strength;
- одну ключевую причину;
- application state;
- основное действие.

Не повторять одно и то же значение в нескольких badges.

---

## 14. Recommendation UI

Ranking score — внутренний относительный показатель качества совпадения.

Он не является:

- вероятностью победы;
- вероятностью ответа;
- процентом совместимости.

Формат:

`Сильное совпадение · 87/100`

Допустимые strength labels должны быть ограниченным набором, например:

- Очень сильное;
- Сильное;
- Возможное;
- Слабое.

Detail screen:

1. summary;
2. `Почему подходит`;
3. `Что проверить`;
4. основные параметры;
5. информация источника;
6. действия.

Причины должны быть конкретными.

Плохо:
> Хороший заказ для вашего профиля.

Хорошо:
> Требуются FastAPI и PostgreSQL — оба навыка указаны в двух ваших проектах.

Risk:
> В заказе нужен React Native, которого нет в профиле.

---

## 15. Progressive disclosure

В list view показывать только информацию, необходимую для выбора следующего объекта.

Detail view раскрывает контекст.

Advanced configuration скрывается за дополнительным действием.

Не показывать пользователю все возможности системы одновременно.

---

## 16. Statuses

Статусы должны использовать общий словарь.

Для async operations всегда различать:

- idle;
- pending;
- success;
- error.

Для applications использовать backend domain status.

Не создавать визуальные статусы, которых нет в модели данных.

---

## 17. Loading

Использовать:

- skeleton для предсказуемого layout;
- spinner только для компактного локального действия;
- progress, если система реально знает прогресс.

Нельзя заменять весь рабочий экран одной крутилкой, если можно показать structure skeleton.

---

## 18. Empty states

Empty state отвечает:

1. почему здесь пусто;
2. нормально ли это;
3. что можно сделать.

Не использовать декоративные пустые экраны с маркетинговым текстом.

---

## 19. Errors

Ошибка должна говорить:

- что не получилось;
- пострадало ли действие;
- можно ли повторить;
- что пользователь должен сделать.

Технические trace/messages пользователю не показываются.
Recoverable error не должен уничтожать current state.

---

## 20. Confirmation and destructive actions

Подтверждение требуется только для действий с существенными последствиями:

- удаление;
- отключение connection;
- auto-send;
- массовые действия;
- потеря данных.

Не ставить confirmation modal на каждую кнопку.

---

## 21. Motion

Motion используется только для понимания изменения состояния.

Duration: примерно `120–180ms`.

Запрещены длинные page transitions, bouncing CTA и бесконечные decorative animations.
Уважать `prefers-reduced-motion`.

---

## 22. Accessibility

Обязательно:

- semantic HTML;
- keyboard navigation;
- `:focus-visible`;
- минимум `44×44px` touch targets;
- достаточный contrast;
- aria labels для icon actions;
- label для controls;
- состояние не определяется только цветом.

---

## 23. Responsive QA

UI-задача не считается законченной без проверки минимум:

- `360px`;
- `390px`;
- tablet;
- desktop `1280px+`.

Проверять обычный browser, standalone PWA и Telegram WebView для затронутых сценариев.

---

## 24. Content style

Тон:

- короткий;
- рабочий;
- спокойный;
- конкретный.

Не использовать лишние приветствия и AI-маркетинг внутри рабочих экранов.

Один смысл не повторяется в соседних page title, subtitle, card title и notice.
Если subtitle ничего не добавляет — удалить.

---

## 25. Component contract

Повторяемые patterns реализуются через UI primitives.

Минимальный набор:

- `AppButton`
- `AppLinkButton`
- `AppCard`
- `AppBadge`
- `AppField`
- `AppRangeField`
- `AppNotice`
- `AppEmptyState`
- `AppSkeleton`
- `AppPageHeader`
- `AppStat`
- `AppToggle`
- `AppCheckbox`
- `AppSegmentedControl`
- `AppIconButton`
- `AppDialog`

Feature component не создаёт локальную копию существующего primitive.

Если нужен новый системный вариант:

1. проверить существующий primitive;
2. расширить его;
3. обновить этот контракт;
4. только затем использовать новый вариант.

---

## 26. Anti AI-slop rules

Запрещено:

- массивы декоративных KPI;
- карточка внутри карточки без структурной причины;
- огромное количество badges;
- repeated labels;
- random gradients;
- glass;
- tiny text;
- sparkle icon everywhere;
- generic AI copy;
- unnecessary hero sections внутри приложения;
- дублирование одного CTA несколькими способами;
- fake command center aesthetics;
- чрезмерное количество разноцветных surfaces.

Professional workflow всегда важнее декоративности.

---

## 27. Money and recommendation provenance

- исходный бюджет и валюта показываются всегда, если они есть в источнике;
- RUB-normalized сумма показывается только при подтверждённом курсе и сопровождается датой;
- при неизвестном курсе используется `AppNotice` с коротким текстом «Деньги требуют проверки»;
- score пишется как rank `/100`, никогда как вероятность;
- detail screen показывает понятный метод подбора: «семантическая модель» или «резервное сравнение»;
- технические fact IDs доступны данным, но не заменяют человекочитаемую причину.
