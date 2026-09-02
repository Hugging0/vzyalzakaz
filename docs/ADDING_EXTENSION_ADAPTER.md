# Добавление площадки в Browser Extension

Добавление площадки должно оставаться локальным изменением adapter layer.

1. В `config/sources.yaml` задайте `submission_type: browser_extension`, уникальный `adapter_id`, минимальный `application_hosts` и честные capabilities. Не включайте collector, пока он отдельно не проверен.
2. Добавьте конфигурацию через `createMarketplaceAdapter` в `extension/src/adapters/marketplaces.ts`. Все URL patterns, selectors, подписи полей, auth markers и success markers должны находиться там.
3. Добавьте только нужные host patterns в `extension/wxt.config.ts` и content-script matches. `<all_urls>` запрещён.
4. Если общей semantic field engine недостаточно, расширьте её нейтральным механизмом. Не добавляйте `if source === ...` в background, content или PWA.
5. Добавьте unit fixtures: поддерживаемый/чужой URL, auth required, форма, controlled input, неизвестное обязательное поле и отсутствие Submit.
6. На тестовом аккаунте вручную проверьте job page, login recovery, SPA navigation, partial fill, reload/restart и success detection после ручной отправки.
7. Обновите `docs/BROWSER_EXTENSION_ARCHITECTURE.md`, если меняется контракт, и `DESIGN.md`, если меняются UI primitives.

Минимальные критерии готовности: URL allowlist на backend и extension совпадает; форма находится устойчивыми selector-группами; обязательные неизвестные поля не угадываются; ошибка понятна пользователю; ни один кодовый путь не нажимает Submit.
