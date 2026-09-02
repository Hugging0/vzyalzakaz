# Browser Extension architecture

Статус: реализованный production-контракт Chromium Extension. Визуальные правила находятся в `DESIGN.md`, frontend-правила — в `docs/FRONTEND_RULES.md`.

## Граница ответственности

PWA создаёт персонализированный отклик и ставит серверную `ApplicationCommand`. Extension использует только текущую браузерную сессию пользователя, открывает allowlisted job URL, находит форму и заполняет известные поля. Пользователь проверяет результат и сам нажимает Submit.

Расширение никогда:

- не получает и не хранит пароль площадки;
- не читает cookies через browser API;
- не обходит CAPTCHA, MFA или anti-bot protection;
- не нажимает Submit;
- не исполняет удалённый JavaScript и не использует `<all_urls>`;
- не отправляет содержимое страницы и заполненные значения в telemetry.

## Стек и структура

- WXT + React + TypeScript, Manifest V3;
- `entrypoints/background.ts` — heartbeat, command polling, вкладки и восстановление;
- `entrypoints/content.ts` — выполнение команды внутри страницы и подтверждение результата;
- `entrypoints/popup/*` — подключение, состояние и переход к активной форме;
- `src/adapters/*` — единственное место для DOM/URL-логики площадок;
- `src/api.ts`, `src/storage.ts`, `src/contracts.ts` — transport, persistent state и общие типы;
- `src/ui/primitives.tsx` — extension-эквиваленты зафиксированных `App*` primitives.

WXT формирует Chrome MV3 manifest. Изоляция core от Chrome-specific entrypoints сохраняет путь к Firefox, но Firefox packaging и проверка не входят в текущий выпуск.

## Account linking

1. Авторизованный пользователь нажимает «Подключить» в `/app/connections`.
2. Backend создаёт случайный одноразовый link-ticket на 5 минут и сохраняет только hash.
3. Если опубликованный extension ID известен PWA, code передаётся через `externally_connectable`; иначе пользователь вставляет code в popup.
4. Extension обменивает code и собственный `installationId` на отдельный opaque token.
5. Backend хранит только token hash. Сессия ограничена TTL, отзывается из PWA и не совпадает с web/Telegram session.

Состояния extension: `CONNECTED`, `DISCONNECTED`, `SESSION_EXPIRED`, `REAUTH_REQUIRED`. PWA агрегирует установки в `CONNECTED`, `OFFLINE`, `NOT_DETECTED`.

Для автоматического linking после публикации задайте `NEXT_PUBLIC_EXTENSION_ID` при сборке frontend. Ручной одноразовый code остаётся рабочим fallback для unpacked и store builds.

## Delivery и восстановление

Backend является source of truth. `ApplicationCommand` принадлежит пользователю, имеет UUID, idempotency key, allowlisted `source_id/job_url`, TTL и `claimed_installation_id`.

```text
queued → delivered → opening_page → page_ready → form_found → filling
                                      ↓                         ↓
                               waiting_for_auth       partially_filled
                                                               ↓
                                                     ready_for_review → submitted
```

Из каждого активного шага возможны `failed`, `cancelled` или `expired` согласно серверной таблице переходов. Повтор одинакового состояния безопасен. Терминальная команда не исполняется повторно.

MV3 service worker не считается постоянно живым. `chrome.alarms` будит его раз в 30 секунд; каждое состояние хранится в `chrome.storage.local`. PWA после постановки команды пробует отправить `CHECK_NOW`, но polling остаётся обязательным fallback. После рестарта браузера расширение получает активную claimed command и продолжает с допустимого этапа.

## Адаптеры

`SiteAdapter` определяет поддержку URL, страницу, auth state, форму, заполнение, capabilities и признак успешной ручной отправки. Реализованы:

- `freelancer_com`;
- `freelance_ru`;
- `fl_ru`;
- `kwork_projects`.

Селекторы сначала используют стабильные attributes/name/test ids, затем русские и английские label patterns. Значения записываются нативным setter и подтверждаются событиями `input`, `change`, `blur`, что совместимо с React/Vue controlled inputs. Неизвестные обязательные поля остаются пустыми и попадают в `attentionFields`.

DOM площадок меняется без нашего релиза, поэтому «адаптер реализован» не равно «навсегда исправен». Перед публикацией новой версии нужен smoke-test на реальном авторизованном аккаунте каждой площадки без финального Submit.

## Безопасность и данные

- Backend повторно проверяет владельца lead и installation для каждой команды.
- Job URL обязан быть HTTPS и совпадать с `application_hosts`; userinfo запрещён.
- Host permissions ограничены четырьмя marketplace domains и API `vzyalzakaz.ru`.
- Content script получает только конкретный command payload.
- Diagnostics принимает фиксированные event names и allowlisted metadata keys; тексты отклика, DOM, ответы и токены отбрасываются.
- Ошибки типизированы: auth, unsupported source/page, missing/changed form, validation, page load, expiry и backend availability.

## Release checklist

```bash
cd extension
npm ci
npm test
npm run typecheck
npm run build
npm run zip
```

Перед Chrome Web Store:

1. проверить четыре площадки на отдельном тестовом профиле;
2. подтвердить, что Submit ни при каких сценариях не вызывается;
3. подготовить privacy policy и disclosure запрашиваемых host permissions;
4. зафиксировать постоянный extension ID и добавить его как `NEXT_PUBLIC_EXTENSION_ID`;
5. пересобрать и задеплоить PWA только из pushed commit;
6. подписать store artifact и сохранить номер версии/commit в release notes.

Публикация в Chrome Web Store требует аккаунта владельца и ручного review и не выполняется из CI проекта.

До публикации в Store frontend Docker build сам выполняет `npm run zip` для
текущего extension-кода и кладёт результат в
`/downloads/vzyalzakaz-extension-chromium.zip`. PWA показывает эту ссылку на экране
«Площадки» вместе с короткой инструкцией по загрузке распакованной папки. Архив не
хранится в Git, поэтому скачиваемая сборка всегда соответствует развёрнутому
commit. Этот путь предназначен для тестирования: штатная установка в один клик на
macOS и Windows возможна только из Chrome Web Store. Та же store-сборка
устанавливается в Яндекс Браузер. Safari требует отдельной упаковки Web Extension и
публикации через App Store.
