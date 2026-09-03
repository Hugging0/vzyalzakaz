# Recommendation architecture

Статус: обязательный backend-контракт с 2026-09-02.

## Граница глобального ingestion

```text
collect → normalize → deduplicate → classify demand/supply → extract neutral facts → persist
```

`OpportunityPipeline` не получает `CandidateProfile`, портфолио или настройки владельца. В `Opportunity` сохраняются исходник, классификация и один переиспользуемый `OpportunityFacts`. Глобальные поля старого персонального scoring остаются только ради совместимости схемы и всегда очищаются.

Допустимые причины глобального reject:

- пустой или невалидный контент;
- supply-side публикация;
- spam/scam с высокой уверенностью;
- истинный дубликат;
- нарушение политики источника.

`unknown` сохраняется, но не участвует в подборе до demand-классификации. Навык, бюджет, доступность, язык пользователя и предпочитаемый формат никогда не являются глобальным фильтром.

## Нейтральные факты

`OpportunityFacts` извлекается один раз и не содержит оценки кандидата: title, work type, category, skills/technologies, seniority, deliverables, raw/normalized budget, currency, duration, effort range, remote/time-zone/meeting constraints, explicit language requirements, client/competition facts, deadline, contacts, risks, source confidence и evidence.

Если LLM недоступна или возвращает невалидный ответ, используется детерминированный extractor. Текст источника считается недоверенными данными и не может давать инструкции модели.

## Персональная рекомендация

```text
OpportunityFacts
  → A. cheap eligibility
  → B. semantic candidate retrieval
  → C. deterministic features
  → D. optional LLM rerank только top-K
  → E. UserOpportunity + UserMatchAnalysis
```

A проверяет только ограничения конкретного пользователя: excluded terms, selected sources/formats, remote, очевидный budget floor, невозможный язык, full-time/office/relocation/daytime calls.

B использует семантическое сходство профиля, навыков, результата задачи и портфолио. Exact skill не является обязательным: смежная capability может пройти retrieval.

C сохраняет feature vector: semantic similarity, skill overlap, portfolio similarity, economics, freshness, format, availability, client attractiveness и timing. Итог — rank `/100`, не вероятность.

D получает только уже отобранный top-K, может скорректировать балл не более чем на восемь пунктов и обязан использовать разрешённые fact IDs. При outage остаётся детерминированный hybrid score. Legacy `personalized_match_score` сохранён только как аварийный fallback и не вызывается штатным pipeline.

E хранит в `UserOpportunity` персональный score, confidence, feature vector, dimensions, причины, проверки, выбранный кейс и версию ranking. `Opportunity` не меняется от результатов пользователя.

## Объяснимость

`MatchEvidence` валиден только при наличии `source_facts` или `profile_facts`. UI отображает силу совпадения и `/100`, измерения, `Почему рекомендуем` и `Что проверить`. Пользовательские статусы и уведомления читаются только из принадлежащего ему `UserOpportunity`.

## Backfill и эксплуатация

После migration `0008_hybrid_recommendations` выполнить:

```bash
python -m app.rebuild_recommendations
```

Команда детерминированно пересобирает neutral facts и объяснения исторических matches без изменения их workflow-статусов или откликов. Затем она удаляет только ещё не обработанные `recommended` matches и строит их заново для активных пользователей. `--llm-facts` разрешает дорогой LLM backfill; без флага новые ingestion всё равно используют настроенный LLM, а исторические данные обрабатываются безопасным fallback.
