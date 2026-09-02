# Hunt Agent — ближайшие продуктовые улучшения

## Web/PWA sprint — 2026-09-01

- Colorblock Studio закреплён как единый Web/PWA/Telegram UI-контракт.
- Онбординг переведён с команд и трёх экранов на один свободный рассказ о себе.
- Бот принимает текст, локально расшифровывает голос и сохраняет необязательные PDF/DOCX/TXT/MD портфолио.
- Inline-кнопки используют Bot API styles `primary`, `success`, `danger` через общий builder.
- Основной интерфейс переведён на responsive routes с desktop sidebar, mobile navigation и PWA shell.
- Добавлены собственная HttpOnly web session, одноразовый вход через бота и context-preserving deep links.
- Воронка и журнал отклика используют общую backend-domain логику для Web и Telegram.
- Источники получили `submission_type` и `capabilities`; UI готов показывать будущие extension connections без хардкода.
- ЮKassa остаётся в тестовом режиме.

Визуальный QA этой миграции выполняет владелец. До production deployment нужно исправить его замечания и проверить responsive layout в реальных браузерах.

## Следующий полезный релиз

1. **Качество лидов.** Ввести source health, spam/risk score, deny-list клиентов
   и пользовательскую обратную связь после Skip. Это повысит signal-to-noise
   раньше, чем рост количества источников.
2. **Browser Extension MVP.** Реализовать локальную авторизацию extension, adapters
   для Freelance.ru/FL.ru/Kwork, получение готового текста и остановку перед Submit.
   Cookies и пароли площадок не должны покидать браузер пользователя.
3. **Профессии.** Отдельные onboarding presets для SMM, video/motion, design,
   copywriting и marketing: навыки, keywords, stop-words, portfolio fields и
   tone отклика. Общая форма не должна заставлять видеомонтажёра мыслить как
   backend-разработчика.
4. **Качество источников.** Показать пользователю, откуда пришёл каждый лид,
   свежесть и дубли; позволить включать источники по профессии. Перед массовым
   включением Telegram-каналов вести метрику полезных лидов на источник.
5. **Монетизация.** До production-биллинга определить тарифы, entitlement rules,
   grace period, отмену/возврат и 54-ФЗ/политику обработки данных. ЮKassa checkout
   уже изолирован на backend и готов к этим правилам.

## Не включать раньше времени

- автоотправку без source-level capabilities и backend guardrails;
- парсинг закрытых площадок или обход CAPTCHA;
- «успешные» статусы до подтверждённого внешнего действия;
- широкое распространение тестовых credentials или публичный Web/PWA без HTTPS.
