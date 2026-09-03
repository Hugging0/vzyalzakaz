# Recommendation architecture

Статус: обязательный backend-контракт с 2026-09-03.

## Global ingestion boundary

```text
collect → normalize → deduplicate → classify demand/supply
→ extract candidate-neutral facts → persist
```

`OpportunityPipeline` не получает профиль, портфолио или настройки владельца. Глобально
разрешены только reject для пустого/невалидного контента, true duplicate, supply-side,
spam/scam с высокой уверенностью и явного нарушения source policy. `unknown` сохраняется.
Навыки, бюджет, доступность, язык и формат конкретного пользователя глобальными фильтрами
не являются.

`Opportunity` хранит только источник, классификацию и нейтральный `OpportunityFacts`.
Персональные score, объяснения, proposal и workflow живут в `UserOpportunity`. Миграция
`0009_semantic_retrieval` физически удаляет прежние candidate-specific поля из глобальной
таблицы.

## OpportunityFacts v2

Facts извлекаются один раз из недоверенного текста и включают title, work type, category,
skills/technologies, seniority, deliverables, duration, effort range, explicit language,
remote/time-zone/meeting constraints, client/competition facts, deadline, contacts, risks,
source confidence и evidence. Язык публикации не превращается в language requirement.

LLM получает строгую JSON schema и не видит кандидата. Невалидный ответ или outage переводит
extraction на deterministic fallback.

### Multi-currency normalization

Исходные `budget_min`, `budget_max`, `currency` и `budget_raw` сохраняются без потери. Для
сравнения добавляются `normalized_budget_*_rub`, `fx_rate_to_rub`, `fx_rate_date`,
`fx_rate_source` и `fx_status`.

`FxRateProvider` отделён от extraction. Штатный `CbrFxRateProvider` запрашивает официальный
daily XML Банка России с timeout и cache на дату; в тестах используется только injected
provider. Отсутствующий или неизвестный курс не вызывает hard reject: economics получает
нейтральную оценку, а UI показывает «требует проверки». Нормализованная сумма показывается
только при известном курсе, исходная валюта — всегда.

## Retrieval implementation

```text
OpportunityFacts
  → A. cheap user eligibility
  → B. cached semantic retrieval, top-K
  → C. deterministic feature builder and versioned rank policy
  → D. bounded LLM rerank for top candidates only
  → E. UserOpportunity + provenance
```

Stage A проверяет только user-specific hard constraints: excluded terms, source/format,
remote, office/relocation/full-time/daytime calls, очевидный сопоставимый budget floor и
невозможный explicit language.

Stage B использует `EmbeddingProvider`. Реализация `OpenAICompatibleEmbeddingProvider`
работает через `POST /embeddings`; base URL, model, timeout и batch size задаются в
`AppSettings`. Профиль включает about, primary/secondary skills и портфолио. Opportunity input
строится из нейтральных facts. `SemanticRepresentation` кэширует нормализованные vectors по
entity, provider, model, retrieval version и input hash:

- opportunity embedding считается один раз на версию facts/text;
- profile embedding переиспользуется и меняется при изменении релевантных полей/портфолио;
- ответы проверяются на count, dimensions, numeric finite values и non-zero norm до записи;
- частичный невалидный batch откатывается;
- edited opportunity удаляет semantic cache и только pending recommendations.

При disabled/outage/invalid embedding используется отдельный `lexical_fallback_v2` с
word/character features и общей capability ontology. Это режим деградации, а не параллельный
primary scoring engine. В штатном embedding mode итог retrieval сочетает semantic vector и
малую lexical component. Только top-K передаётся дорогому feature/rank слою.

Stage C сохраняет vector `semantic_retrieval`, skill overlap, portfolio similarity, economics,
freshness, format, availability, client attractiveness и timing. Все веса живут в одном
`RankingPolicy`, имеют версию `hybrid-v2` и в сумме равны 1. Старые пользовательские weight
поля и `personalized_match_score` удалены.

Stage D применяется только к верхним `matching_llm_rerank_top_k`, меняет score максимум на
8 пунктов и принимает только разрешённые source/profile fact IDs. Outage оставляет
детерминированный результат.

Stage E хранит rank `/100` (не вероятность), confidence, dimensions, reasons, checks,
retrieval method/fallback, evidence provenance, rerank flag и версии алгоритмов.

## Rebuild and operations

После migration `0009_semantic_retrieval`:

```bash
python -m app.rebuild_recommendations --batch-size 200
```

Rebuild идемпотентно и пакетно обновляет только устаревшие facts, продолжает после единичной
ошибки, сохраняет actioned workflow/proposal/history, удаляет только `recommended`, затем
сканирует полный глобальный corpus для каждого активного пользователя. Onboarding limit к
admin rebuild не применяется. `--llm-facts` явно включает дорогой исторический extraction.

Логи batch содержат только counters/latency: scanned, eligibility rejected, retrieval
candidates, ranked, persisted, rerank count, cache hits/misses и fallback. Исходный текст,
профили и секреты в логи не выводятся.

## Evaluation boundary

`tests/fixtures/retrieval_evaluation.yaml` — маленький synthetic regression corpus по backend,
frontend, design, marketing, video, content и automation. Gate: Precision@10 ≥ 0.80,
Recall@10 = 1.0 и отсутствие miss для вручную отмеченных adjacent cases. Отдельные тесты
проверяют реальный provider path на семантической паре без общих токенов, cache invalidation,
outage и malformed vectors.

Это инженерный regression corpus, а не оценка качества на production-трафике. Для продуктовой
калибровки нужны обезличенные реальные решения пользователей и более широкий ручной benchmark.
