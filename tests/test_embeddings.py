import json

import httpx
import pytest

from app.services.embeddings import EmbeddingError, build_embedding_provider


@pytest.fixture
def timeweb_provider(settings):
    settings.embedding_provider = "timeweb_yandex"
    settings.embedding_api_key = "test-timeweb-key"
    return build_embedding_provider(settings)


def intercept_requests(monkeypatch, handler):
    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs),
    )


@pytest.mark.asyncio
async def test_timeweb_uses_single_strings_and_distinct_query_model(monkeypatch, timeweb_provider):
    requests = []

    def handler(request):
        assert str(request.url) == "https://api.timeweb.ai/v1/embeddings"
        assert request.headers["Authorization"] == "Bearer test-timeweb-key"
        body = json.loads(request.content)
        assert isinstance(body["input"], str)
        assert "encoding_format" not in body
        requests.append(body)
        vector = [3.0, 4.0] if body["input"] == "first order" else [0.0, 2.0]
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": vector}]})

    intercept_requests(monkeypatch, handler)
    documents = await timeweb_provider.embed(["first order", "second order"])
    query = await timeweb_provider.embed(["candidate profile"], purpose="query")

    assert documents == [[0.6, 0.8], [0.0, 1.0]]
    assert query == [[0.0, 1.0]]
    assert [body["model"] for body in requests] == [
        "yandex/text-embeddings-v2-doc",
        "yandex/text-embeddings-v2-doc",
        "yandex/text-embeddings-v2-query",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["outage", "malformed", "dimensions", "zero"])
async def test_timeweb_rejects_entire_batch_after_partial_success(
    monkeypatch, timeweb_provider, failure
):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"data": [{"embedding": [1.0, 0.0]}]})
        if failure == "outage":
            return httpx.Response(503, json={"error": {"message": "Unavailable"}})
        if failure == "malformed":
            return httpx.Response(200, json={"data": [None]})
        vector = [1.0, 0.0, 0.0] if failure == "dimensions" else [0.0, 0.0]
        return httpx.Response(200, json={"data": [{"embedding": vector}]})

    intercept_requests(monkeypatch, handler)
    with pytest.raises(EmbeddingError):
        await timeweb_provider.embed(["first order", "second order"])
    assert calls == 2
