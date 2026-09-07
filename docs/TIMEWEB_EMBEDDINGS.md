# Timeweb Yandex embeddings

The embedding provider is `timeweb_yandex`. Requests go directly to
`https://api.timeweb.ai/v1/embeddings`; the private Telegram SOCKS5 proxy is not used.

- Opportunity facts use `yandex/text-embeddings-v2-doc`.
- The candidate profile, skills and portfolio use `yandex/text-embeddings-v2-query`.
- Both models returned 256-dimensional vectors in the live connection check.
- Each HTTP request contains a single string. Testing two-element arrays returned
  503, whereas string input worked with both models.
- Cache entries identify the actual query/document model. Changing query models
  invalidates profile cache reuse without discarding valid document vectors.
- API failures retain the deterministic lexical fallback. This is an outage path,
  not a second external embedding provider.

## Deployment configuration

Set these variables in the private server `.env`:

```dotenv
EMBEDDING_PROVIDER=timeweb_yandex
EMBEDDING_API_KEY=<Timeweb AI Gateway key>
EMBEDDING_BASE_URL=https://api.timeweb.ai/v1
EMBEDDING_MODEL=yandex/text-embeddings-v2-doc
EMBEDDING_QUERY_MODEL=yandex/text-embeddings-v2-query
```

The previous embedding credentials and endpoint settings must be removed from the
active configuration. DeepSeek remains the separate text-generation/reranking
provider; Telegram proxy credentials are unrelated and must be preserved.

Recreate the backend container after deploying the pushed commit. No database
migration or frontend/extension build is required. Existing recommendations are
not bulk-rewritten during deployment. New retrievals use the configured provider;
cache is populated on demand.

The deployment branch starts from `d4b51f6`, the previously deployed version.
The newer HeadHunter integration on `main` is intentionally outside this change.

## Verification and rollback

Run `ruff check app tests migrations` and `pytest -q`. The tests cover single-string
requests, query/doc model routing, normalization, partial batch failures, cache
invalidation and fallback behaviour.

Verify the live provider from the rebuilt backend container, then exercise
`CandidateRetriever` with a bounded set of orders and check `fallback_used=False`
and cache reuse. Do not send user notifications or client proposals during checks.

Git rollback does not restore `.env`. To return to `d4b51f6`, set
`EMBEDDING_PROVIDER=disabled` before recreating the old backend. Generated semantic
cache may remain: it is isolated by provider and model. No old provider credentials
are needed for this rollback.
