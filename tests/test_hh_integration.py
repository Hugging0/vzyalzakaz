from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import SourceConfig
from app.database import make_engine
from app.integrations.hh.application_provider import HHApplicationProvider
from app.integrations.hh.client import HHClient
from app.integrations.hh.collector import HHCollector
from app.integrations.hh.errors import HHError, error_from_response
from app.integrations.hh.mapper import map_vacancy
from app.integrations.hh.oauth import (
    TokenCipher,
    access_token_for,
    create_oauth_authorization,
    finish_oauth,
)
from app.integrations.hh.router import hh_oauth_callback
from app.models import (
    ApplicationAttempt,
    ApplicationCommand,
    Base,
    ExternalConnection,
    ExternalConnectionStatus,
    IntegrationAuditEvent,
    Opportunity,
    OpportunityStatus,
    TelegramUser,
    UserOpportunity,
)
from app.schemas import OpportunityFacts
from app.services.pipeline import OpportunityPipeline
from app.services.retrieval import CandidateRetriever


def hh_settings(settings):
    return settings.model_copy(
        update={
            "hh_client_id": "client-id",
            "hh_client_secret": "client-secret",
            "hh_token_encryption_key": Fernet.generate_key().decode(),
            "public_base_url": "https://vzyalzakaz.test",
        }
    )


def vacancy(**overrides):
    payload = {
        "id": "123",
        "name": "Python developer",
        "description": "<p>FastAPI and PostgreSQL</p>",
        "alternate_url": "https://hh.ru/vacancy/123",
        "employer": {"name": "Acme"},
        "salary": {"from": 150000, "to": 220000, "currency": "RUR"},
        "schedule": {"id": "remote"},
        "employment": {"id": "full"},
        "area": {"name": "Москва"},
        "key_skills": [{"name": "Python"}, {"name": "FastAPI"}],
        "published_at": "2026-09-04T12:00:00+03:00",
        "relations": [],
        "negotiations_url": "https://api.hh.ru/negotiations?vacancy_id=123",
        "suitable_resumes_url": "https://api.hh.ru/vacancies/123/suitable_resumes",
    }
    payload.update(overrides)
    return payload


def test_hh_mapper_preserves_neutral_facts_and_provider_metadata():
    source = SourceConfig(name="hh_ru", type="api", collector="hh")
    raw = map_vacancy(vacancy(), source, allow_external_llm=False)

    assert raw.source_type == "api"
    assert raw.external_id == "123"
    assert raw.description == "FastAPI and PostgreSQL"
    assert raw.skills == ["Python", "FastAPI"]
    assert raw.currency == "RUB"
    assert raw.remote is True
    assert raw.metadata["external_ai_allowed"] is False
    assert raw.metadata["provider_metadata"]["provider"] == "hh"


class FakeHHClient:
    def __init__(self, vacancy_payload=None, suitable=None, apply_error=None):
        self.vacancy_payload = vacancy_payload or vacancy()
        self.suitable_payload = suitable if suitable is not None else {"items": [{"id": "resume-1"}]}
        self.apply_error = apply_error
        self.apply_calls = 0

    async def exchange_code(self, code, redirect_uri):
        assert code == "oauth-code"
        assert redirect_uri.endswith("/api/integrations/hh/oauth/callback")
        return {"access_token": "access-secret", "refresh_token": "refresh-secret", "expires_in": 3600}

    async def me(self, access_token):
        assert access_token == "access-secret"
        return {"id": "hh-user", "first_name": "Анна", "last_name": "Иванова"}

    async def refresh_token(self, refresh_token):
        assert refresh_token == "refresh-secret"
        return {"access_token": "access-new", "refresh_token": "refresh-new", "expires_in": 3600}

    async def vacancy(self, vacancy_id, access_token=None):
        assert vacancy_id == "123"
        return self.vacancy_payload

    async def suitable_resumes(self, vacancy_id, access_token):
        return self.suitable_payload

    async def apply(self, vacancy_id, resume_id, message, access_token):
        self.apply_calls += 1
        if self.apply_error:
            raise self.apply_error
        return {"id": "negotiation-1"}


@pytest.mark.asyncio
async def test_oauth_state_is_one_time_and_tokens_are_encrypted(settings, profile):
    configured = hh_settings(settings)
    engine = make_engine(configured.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        user = TelegramUser(telegram_user_id=501, profile=profile.model_dump(), portfolio=[])
        session.add(user)
        await session.commit()
        authorize_url = await create_oauth_authorization(session, user, configured)
        state = parse_qs(urlparse(authorize_url).query)["state"][0]
        connected = await finish_oauth(session, state, "oauth-code", configured, client=FakeHHClient())

        assert connected.status == ExternalConnectionStatus.CONNECTED
        assert "access-secret" not in connected.access_token_encrypted
        assert (
            TokenCipher(configured.hh_token_encryption_key).decrypt(connected.access_token_encrypted)
            == "access-secret"
        )
        with pytest.raises(HHError) as reused:
            await finish_oauth(session, state, "oauth-code", configured, client=FakeHHClient())
        assert reused.value.code == "oauth_state_invalid"
    await engine.dispose()


@pytest.mark.asyncio
async def test_oauth_callback_redirects_and_audits_connection(monkeypatch, settings, profile):
    configured = hh_settings(settings)
    engine = make_engine(configured.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as database_connection:
        await database_connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        user = TelegramUser(telegram_user_id=510, profile=profile.model_dump(), portfolio=[])
        session.add(user)
        await session.commit()
        connection = ExternalConnection(user_id=user.id, provider="hh")

        async def fake_finish(*_args, **_kwargs):
            return connection

        async def fake_refresh(*_args, **_kwargs):
            return None

        monkeypatch.setattr("app.integrations.hh.router.finish_oauth", fake_finish)
        monkeypatch.setattr("app.integrations.hh.router._refresh_resumes", fake_refresh)
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(runtime=SimpleNamespace(settings=configured)))
        )

        response = await hh_oauth_callback(request, "s" * 32, "oauth-code", None, session)

        assert response.status_code == 303
        assert response.headers["location"].endswith("/app/connections?hh=connected")
        event = await session.scalar(select(IntegrationAuditEvent))
        assert event is not None
        assert event.event == "connected"
        assert event.user_id == user.id
    await engine.dispose()


def test_hh_revoked_token_error_requires_reauthorization():
    response = httpx.Response(
        403,
        json={"errors": [{"type": "oauth", "value": "token-revoked"}]},
        request=httpx.Request("GET", "https://api.hh.ru/me"),
    )

    error = error_from_response(response)

    assert error.code == "auth_required"


@pytest.mark.asyncio
async def test_hh_application_server_error_is_uncertain_and_not_retried(settings):
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={"errors": [{"type": "service_unavailable"}]})

    client = HHClient(hh_settings(settings), transport=httpx.MockTransport(handler))

    with pytest.raises(HHError) as error:
        await client.apply("123", "resume-1", "Здравствуйте", "access-token")

    assert error.value.code == "uncertain"
    assert calls == 1


@pytest.mark.asyncio
async def test_expired_token_is_refreshed_and_revoked_token_requires_reauth(settings, profile):
    configured = hh_settings(settings)
    engine = make_engine(configured.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        user = TelegramUser(telegram_user_id=502, profile=profile.model_dump(), portfolio=[])
        cipher = TokenCipher(configured.hh_token_encryption_key)
        session.add(user)
        await session.flush()
        connection = ExternalConnection(
            user_id=user.id,
            provider="hh",
            access_token_encrypted=cipher.encrypt("access-old"),
            refresh_token_encrypted=cipher.encrypt("refresh-secret"),
            token_expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        session.add(connection)
        await session.commit()

        token = await access_token_for(session, connection, configured, client=FakeHHClient())
        assert token == "access-new"
        assert cipher.decrypt(connection.refresh_token_encrypted) == "refresh-new"

        connection.token_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
        broken = FakeHHClient()

        async def fail_refresh(_token):
            raise HHError("auth_required", "expired", 401)

        broken.refresh_token = fail_refresh
        with pytest.raises(HHError) as expired:
            await access_token_for(session, connection, configured, client=broken)
        assert expired.value.code == "auth_required"
        assert connection.status == ExternalConnectionStatus.REAUTH_REQUIRED
        assert connection.access_token_encrypted is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_hh_collector_paginates_details_and_deduplicates(monkeypatch, settings):
    configured = hh_settings(settings)
    source = SourceConfig(
        name="hh_ru",
        type="api",
        collector="hh",
        options={"max_pages": 3, "per_page": 2, "period_days": 2},
    )

    class CollectorClient:
        def __init__(self, _settings):
            self.pages = 0

        async def search_vacancies(self, params):
            self.pages += 1
            return {
                "pages": 2,
                "items": [{"id": "123"}, {"id": "123"}] if params["page"] == 0 else [{"id": "124"}],
            }

        async def vacancy(self, vacancy_id):
            return vacancy(id=vacancy_id, alternate_url=f"https://hh.ru/vacancy/{vacancy_id}")

    monkeypatch.setattr("app.integrations.hh.collector.HHClient", CollectorClient)
    items = await HHCollector(source, configured).fetch_new()

    assert [item.external_id for item in items] == ["123", "124"]
    assert all(item.metadata["external_ai_allowed"] is False for item in items)


@pytest.mark.asyncio
async def test_hh_incremental_collector_skips_persisted_vacancy_details(monkeypatch, settings):
    configured = hh_settings(settings)
    source = SourceConfig(name="hh_ru", type="api", collector="hh", options={"max_pages": 1})
    detail_calls = []

    class CollectorClient:
        def __init__(self, _settings):
            pass

        async def search_vacancies(self, _params):
            return {"pages": 1, "items": [{"id": "123"}, {"id": "124"}]}

        async def vacancy(self, vacancy_id):
            detail_calls.append(vacancy_id)
            return vacancy(id=vacancy_id, alternate_url=f"https://hh.ru/vacancy/{vacancy_id}")

    monkeypatch.setattr("app.integrations.hh.collector.HHClient", CollectorClient)
    engine = make_engine(configured.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as database_connection:
        await database_connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        session.add(
            Opportunity(
                source="hh_ru",
                source_type="api",
                external_id="123",
                title="Existing",
                description="Existing",
                raw_text="Existing",
                normalized_hash="existing-hh",
            )
        )
        await session.commit()

        items = await HHCollector(source, configured).fetch_incremental(session)

        assert [item.external_id for item in items] == ["124"]
        assert detail_calls == ["124"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_hh_pipeline_deduplicates_same_external_vacancy(settings):
    engine = make_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    source = SourceConfig(name="hh_ru", type="api", collector="hh")
    raw = map_vacancy(vacancy(), source, allow_external_llm=False)
    async with factory() as session:
        pipeline = OpportunityPipeline(settings)
        first = await pipeline.process(session, raw)
        second = await pipeline.process(session, raw)
        assert first.created is True
        assert second.created is False
        assert await session.scalar(select(func.count()).select_from(Opportunity)) == 1
        assert first.opportunity.external_ai_allowed is False
    await engine.dispose()


@pytest.mark.asyncio
async def test_hh_content_is_not_sent_to_external_embedding_provider(settings, profile):
    class RecordingProvider:
        available = True
        name = "recording"
        model = "test"

        def __init__(self):
            self.inputs = []

        async def embed(self, texts):
            self.inputs.extend(texts)
            return [[1.0, 0.0] for _ in texts]

    engine = make_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        user = TelegramUser(telegram_user_id=509, profile=profile.model_dump(), portfolio=[])
        hh = Opportunity(
            source="hh_ru",
            source_type="api",
            external_id="private-hh",
            title="HH confidential phrase",
            description="HH confidential phrase",
            raw_text="HH confidential phrase",
            normalized_hash="private-hh",
            external_ai_allowed=False,
        )
        public = Opportunity(
            source="public",
            source_type="api",
            external_id="public",
            title="Public vacancy phrase",
            description="Public vacancy phrase",
            raw_text="Public vacancy phrase",
            normalized_hash="public",
            external_ai_allowed=True,
        )
        session.add_all([user, hh, public])
        await session.commit()
        provider = RecordingProvider()
        facts = [
            (hh, OpportunityFacts(title=hh.title)),
            (public, OpportunityFacts(title=public.title)),
        ]
        results = await CandidateRetriever(settings, provider=provider).retrieve(
            session, user, profile, [], facts
        )

        assert not any("HH confidential phrase" in value for value in provider.inputs)
        assert any("Public vacancy phrase" in value for value in provider.inputs)
        hh_result = next(item for item in results if item.opportunity.id == hh.id)
        assert hh_result.embedding_score is None
        assert hh_result.fallback_used is True
    await engine.dispose()


async def application_records(session, configured, profile):
    user = TelegramUser(telegram_user_id=503, profile=profile.model_dump(), portfolio=[])
    opportunity = Opportunity(
        source="hh_ru",
        source_type="api",
        source_url="https://hh.ru/vacancy/123",
        external_id="123",
        title="Python developer",
        description="FastAPI",
        raw_text="FastAPI",
        normalized_hash="hh-123",
        provider_metadata={"provider": "hh", "negotiations_url": "https://api.hh.ru/negotiations"},
        external_ai_allowed=False,
    )
    session.add_all([user, opportunity])
    await session.flush()
    match = UserOpportunity(
        user_id=user.id,
        opportunity_id=opportunity.id,
        proposal="Здравствуйте! Готов обсудить задачу.",
        status=OpportunityStatus.APPROVED,
    )
    cipher = TokenCipher(configured.hh_token_encryption_key)
    connection = ExternalConnection(
        user_id=user.id,
        provider="hh",
        access_token_encrypted=cipher.encrypt("access-secret"),
        refresh_token_encrypted=cipher.encrypt("refresh-secret"),
        token_expires_at=datetime.now(UTC) + timedelta(hours=1),
        selected_resume_id="resume-1",
        metadata_json={"resumes": [{"id": "resume-1", "title": "Python developer"}]},
    )
    session.add_all([match, connection])
    await session.commit()
    source = next(item for item in configured.load_sources() if item.name == "hh_ru")
    return user, opportunity, match, source


@pytest.mark.asyncio
async def test_hh_application_success_and_idempotency(settings, profile):
    configured = hh_settings(settings)
    engine = make_engine(configured.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        user, opportunity, match, source = await application_records(session, configured, profile)
        client = FakeHHClient()
        provider = HHApplicationProvider(configured, client=client)
        first = await provider.submit(session, user, match, opportunity, source, "request-123")
        second = await provider.submit(session, user, match, opportunity, source, "request-123")

        assert first.status == "submitted"
        assert second.status == "submitted"
        assert client.apply_calls == 1
        assert match.status == OpportunityStatus.CONTACTED
        assert await session.scalar(select(func.count()).select_from(ApplicationAttempt)) == 1
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("vacancy_payload", "suitable", "expected"),
    [
        (vacancy(relations=["got_response"]), {"items": [{"id": "resume-1"}]}, "already_applied"),
        (vacancy(test={"required": True}), {"items": [{"id": "resume-1"}]}, "external_action_required"),
        (vacancy(), {"items": [{"id": "another-resume"}]}, "failed"),
    ],
)
async def test_hh_application_domain_outcomes(settings, profile, vacancy_payload, suitable, expected):
    configured = hh_settings(settings)
    engine = make_engine(configured.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        user, opportunity, match, source = await application_records(session, configured, profile)
        provider = HHApplicationProvider(
            configured,
            client=FakeHHClient(vacancy_payload=vacancy_payload, suitable=suitable),
        )
        result = await provider.submit(session, user, match, opportunity, source, "request-456")

        assert result.status == expected
        if expected == "external_action_required":
            assert await session.scalar(select(func.count()).select_from(ApplicationCommand)) == 1
            assert result.command is not None
            refreshed = await provider.status(session, user, match, opportunity)
            assert refreshed.command is not None
        if expected == "failed":
            attempt = await session.scalar(select(ApplicationAttempt))
            assert attempt.error_code == "resume_not_found"
    await engine.dispose()


@pytest.mark.asyncio
async def test_revoked_access_token_marks_hh_connection_for_reauthorization(settings, profile):
    configured = hh_settings(settings)
    engine = make_engine(configured.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as database_connection:
        await database_connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        user, opportunity, match, source = await application_records(session, configured, profile)
        client = FakeHHClient()

        async def revoked_vacancy(*_args, **_kwargs):
            raise HHError("auth_required", "Подключение HH устарело.", 401)

        client.vacancy = revoked_vacancy
        result = await HHApplicationProvider(configured, client=client).submit(
            session, user, match, opportunity, source, "request-revoked"
        )
        connection = await session.scalar(select(ExternalConnection))

        assert result.status == "connection_required"
        assert connection.status == ExternalConnectionStatus.REAUTH_REQUIRED
        assert connection.access_token_encrypted is None
        assert connection.refresh_token_encrypted is None
    await engine.dispose()
