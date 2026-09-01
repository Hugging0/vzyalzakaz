# Источники проектов и вакансий

Актуально на 1 сентября 2026 года по production `tg.vzyalzakaz.ru`.

## Краткий статус

| Показатель | Количество |
|---|---:|
| Включено в конфигурации | 49 |
| Telegram-каналы | 33 |
| Web / API / RSS | 16 |
| Отключено в конфигурации | 137 |
| Всего записей в реестре | 186 |
| Автоматически парсится прямо сейчас | **49** |

Production scheduler опрашивает 16 Web / API / RSS-источников. Пользовательский MTProto collector авторизован, подключён через отдельный приватный SOCKS5 и слушает все 33 Telegram-канала. SOCKS5 разрешает подключения только с IP production VPS; Bot API, Mini App, LLM и остальные сервисы идут напрямую. Начальный backfill выполняется последовательно в фоне и не блокирует запуск API.

## Включённые Telegram-источники

### Tier A — разработка и IT

| № | Техническое имя | Канал | Язык | Режим |
|---:|---|---|---|---|
| 1 | `telegram_python_jobs` | `@python_jobs` | RU | Можно отправлять |
| 2 | `telegram_job_python` | `@job_python` | RU | Можно отправлять |
| 3 | `telegram_itfreelancers` | `@itfreelancers` | Multi | Можно отправлять |
| 4 | `telegram_datasciencejobs` | `@datasciencejobs` | RU | Можно отправлять |
| 5 | `telegram_hr_itwork` | `@hr_itwork` | RU | Можно отправлять |
| 6 | `telegram_remote_python_jobs` | `@remote_python_jobs` | EN | Можно отправлять |
| 7 | `telegram_remote_ai_jobs` | `@remote_ai_jobs` | EN | Можно отправлять |
| 8 | `telegram_it_remote_projects` | `@IT_REMOTE_PROJECTS` | Multi | Можно отправлять |
| 9 | `telegram_doorkaari` | `@doorkaari` | FA | Можно отправлять |

### Tier B/C — разработка, DevOps и удалённая работа

| № | Техническое имя | Канал | Язык | Приоритет | Режим |
|---:|---|---|---|---|---|
| 10 | `telegram_devops_jobs_feed` | `@devops_jobs_feed` | RU | B | Можно отправлять |
| 11 | `telegram_devops_jobs` | `@devops_jobs` | RU | B | Можно отправлять |
| 12 | `telegram_jobs_in_it_remoute` | `@jobs_in_it_remoute` | RU | B | Можно отправлять |
| 13 | `telegram_devs_it` | `@devs_it` | RU | B | Можно отправлять |
| 15 | `telegram_refer_me_it` | `@refer_me_it` | RU | B | Можно отправлять |
| 16 | `telegram_vakansii` | `@vakansii` | RU | B | Можно отправлять |
| 17 | `telegram_vacancies_in_english` | `@vacancies_in_english` | EN | B | Можно отправлять |
| 18 | `telegram_remote_devops_jobs` | `@remote_devops_jobs` | EN | B | Можно отправлять |
| 19 | `telegram_remotejobs` | `@remotejobs` | EN | B | Можно отправлять |
| 20 | `telegram_remotejobss` | `@remotejobss` | EN | B | Можно отправлять |
| 21 | `telegram_remoters` | `@remoters` | EN | B | Можно отправлять |
| 22 | `telegram_ai_india_jobs` | `@AiIndiaJobs` | EN | B | Можно отправлять |
| 23 | `telegram_dev_jobs_daily` | `@DevJobsDaily` | EN | B | Можно отправлять |
| 24 | `telegram_freelancer_projects` | `@freelancer_projects` | FA | B | Можно отправлять |
| 25 | `telegram_project_board` | `@Project_board` | FA | B | Можно отправлять |
| 26 | `telegram_freelancer_news` | `@Freelancer_news` | FA | B | Можно отправлять |
| 27 | `telegram_freelance_ethio` | `@freelance_ethio` | EN | C | Можно отправлять |

### Digital, SMM, дизайн, видео и motion

Для этих каналов поддерживается только подготовка черновика. Автоматическая отправка отключена.

| № | Техническое имя | Канал | Язык | Приоритет |
|---:|---|---|---|---|
| 28 | `telegram_smm_vacancies` | `@vacancysmm` | RU | A |
| 29 | `telegram_digital_smm` | `@vakanser_digital_smm` | RU | A |
| 30 | `telegram_designodromo` | `@designodromo` | RU | B |
| 31 | `telegram_motionhunter` | `@motionhunter` | RU | B |
| 32 | `telegram_cgfreelance` | `@cgfreelance` | RU | B |
| 33 | `telegram_general_freelance` | `@frilans` | RU | C |

## Включённые Web / API / RSS-источники

Для всех внешних сайтов поддерживается только подготовка черновика отклика.

| № | Техническое имя | Тип | Категория / endpoint | Интервал по конфигурации |
|---:|---|---|---|---:|
| 34 | `remoteok` | API | `https://remoteok.com/api` | 30 минут |
| 35 | `hackernews` | Web API | Ask HN: Who is hiring? | 6 часов |
| 36 | `weworkremotely` | RSS | Programming jobs | 1 час |
| 37 | `weworkremotely_design` | RSS | Design jobs | 1 час |
| 38 | `weworkremotely_marketing` | RSS | Sales and marketing | 1 час |
| 39 | `jobicy_marketing` | API | Marketing | 6 часов |
| 40 | `jobicy_design_multimedia` | API | Design and multimedia | 6 часов |
| 41 | `jobicy_copywriting` | API | Copywriting | 6 часов |
| 42 | `himalayas` | API | Remote jobs, официальный public API | 24 часа |
| 43 | `freelancer_com` | API | Открытые проекты Freelancer.com | 30 минут |
| 44 | `working_nomads` | API | Remote jobs, публичный JSON feed | 1 час |
| 45 | `problogger_jobs` | Web | Writing / content projects | 3 часа |
| 46 | `python_org_jobs` | RSS | Официальный Python Job Board | 30 минут |
| 47 | `golangprojects` | RSS | Go / Golang jobs | 1 час |
| 48 | `work_with_indies` | RSS | Indie game development | 1 час |
| 49 | `coroflot` | RSS | Design / creative jobs | 6 часов |

## Отключённые источники

| Техническое имя | Источник | Причина / статус |
|---|---|---|
| `hh_ru` | HeadHunter API | Отключён в конфигурации |
| `remotive` | Remotive, Python/automation | HTTP 403 с production VPS |
| `remotive_design` | Remotive, design | HTTP 403 с production VPS |
| `remotive_marketing` | Remotive, marketing | HTTP 403 с production VPS |
| `remotive_writing` | Remotive, writing | HTTP 403 с production VPS |
| `arbeitnow` | Arbeitnow API | HTTP 403 с production VPS |

## Дополнительный каталог

Из переданного списка добавлены все 61 площадка. Четыре уже имеют рабочие адаптеры и включены выше. Ещё 57 зарегистрированы с `enabled: false`: scheduler их не запускает, пока для источника нет стабильного и проверенного способа доступа.

| Группа | Источники | Почему пока выключены |
|---|---|---|
| Россия и СНГ | `freelance_ru`, `fl_ru`, `kwork_projects`, `weblancer`, `workspace_tenders`, `dprofile_projects`, `habr_career`, `getmatch`, `geekjob`, `finder_work_remote`, `rabota_ru_remote`, `freelancehunt`, `workzilla`, `youdo_digital`, `gderabota_remote` | Нужны отдельные HTML/JS-адаптеры, контроль robots/rate limit и наблюдение за стабильностью. У `freelancehunt` сейчас HTTP 403 с production VPS. |
| Международные marketplaces | `upwork`, `peopleperhour`, `guru`, `contra`, `workana`, `malt`, `toptal`, `braintrust`, `arc`, `proxify`, `a_team`, `yunojuno`, `twine`, `freelancermap`, `codeable`, `storetasker`, `designcrowd`, `99designs` | Часть требует аккаунт/vetting, остальные — отдельный публичный web-адаптер. Автоотклик запрещён, только draft flow. |
| Remote / startup boards | `wellfound`, `yc_jobs`, `nodesk`, `remote_co`, `workew`, `flexjobs`, `dynamite_jobs`, `skipthedrive`, `the_muse`, `builtin_remote`, `dice`, `jobspresso`, `justremote`, `jobgether`, `welcome_to_jungle` | Публичные страницы требуют отдельного адаптера и дедупликации; некоторые закрыты платным доступом или аккаунтом. |
| API с ключом | `adzuna_api`, `jooble_api`, `usajobs_api` | Нужны API credentials, quota-aware polling и отдельная конфигурация секретов. |
| Creative / writing | `behance_jobs`, `dribbble_jobs`, `mediabistro`, `bloggingpro_jobs`, `creativepool_jobs`, `the_dots_jobs` | Нужен отдельный web/creative pipeline; часть функций требует аккаунт. |

Полный реестр и интервалы находятся в `config/sources.yaml`. Значение `collector: pending` допустимо только у выключенной записи: включать такую запись до реализации адаптера нельзя.

## Дополнительный каталог — часть 2

Из второй подборки добавлены все 78 уникальных площадок. Запись `otta_wttj_feed` не создавалась: это альтернативный путь к уже зарегистрированному `welcome_to_jungle`, а не самостоятельный источник.

Четыре источника включены через проверенные RSS: `python_org_jobs`, `golangprojects`, `work_with_indies`, `coroflot`. Остальные 74 зарегистрированы с `enabled: false`.

| Группа | Источники | Статус |
|---|---|---|
| Marketplaces / talent networks | `fiverr`, `solidgigs`, `gun_io`, `lemon_io`, `flexiple`, `clouddevs`, `catalant`, `business_talent_group`, `graphite_experts`, `expert360`, `mayple_experts`, `marketerhire`, `contently`, `clearvoice`, `composely`, `designhill_jobs`, `aquent`, `creative_circle`, `freelance_nl`, `hoofdkraan`, `jellow`, `striive` | Нужны account/matching flow либо отдельный web-адаптер. |
| Remote / tech boards | `virtual_vocations`, `remote_woman`, `remote4me`, `powertofly`, `vuejobs`, `justjoinit`, `nofluffjobs`, `landing_jobs`, `eu_remote_jobs`, `devitjobs`, `remote_rocketship`, `tech_jobs_for_good`, `climatebase_jobs`, `startup_jobs`, `flexa_careers`, `dailyremote`, `four_day_week`, `jobfluent` | Нужны отдельные адаптеры и дедупликация. `remote_rocketship` возвращает HTTP 403 с VPS; RSS `remote4me` содержит статьи, а не вакансии. |
| Web3 / AI / gaming | `web3_career`, `remote3`, `cryptojobslist`, `cryptocurrency_jobs`, `laborx`, `ai_jobs_net`, `hitmarker`, `gamejobsremote` | Нужны отдельные web/API-адаптеры. `web3_career` и `cryptojobslist` возвращают HTTP 403 с VPS. |
| Translation / testing / research | `proz_jobs`, `translatorscafe`, `smartcat_marketplace`, `utest_projects`, `testlio`, `testerwork`, `testbirds`, `usertesting`, `user_interviews`, `respondent` | В основном account/matching. `ProZ` возвращает HTTP 403, `uTest` — HTTP 451 с VPS. |
| Российские job boards | `superjob`, `avito_jobs`, `trudvsem`, `careerist`, `gorodrabot` | Нужны отдельные API/web-адаптеры и строгая дедупликация. |
| Тендеры | `b2b_center`, `roseltorg`, `tender_pro`, `rts_tender`, `sberbank_ast`, `mos_supplier_portal`, `eis_zakupki`, `fabrikant`, `tektorg`, `otc_tenders`, `bidzaar` | Нельзя смешивать с вакансиями: нужен tender pipeline с проверкой юрлица, срока, обеспечения и документов. |

## Что уже есть в базе

База постоянно растёт, поэтому точные числа следует получать запросом к production, а не считать этот документ счётчиком. На контрольном снимке после включения MTProto в ней было более 1 500 записей. Первые два обработанных Telegram-канала уже дали 49 сохранённых сообщений; backfill остальных каналов продолжался в фоне.

Контрольные проходы всех 16 Web / API / RSS-источников завершались без ошибок. Для Telegram проверен полный путь: SOCKS5 → production MTProto DC → Telethon → normalization/prefilter → PostgreSQL.

## Где находится конфигурация

Основной файл: `config/sources.yaml`.
