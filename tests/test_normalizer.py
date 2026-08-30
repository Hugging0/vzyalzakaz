from app.schemas import RawOpportunity
from app.services.normalizer import normalize, normalize_text


def test_normalized_hash_ignores_url_and_case():
    first = RawOpportunity(
        source="one", source_type="telegram", external_id="1", raw_text="Python BOT https://a.test/x"
    )
    second = RawOpportunity(
        source="two", source_type="telegram", external_id="2", raw_text="python bot https://b.test/y"
    )
    assert normalize(first).content_hash == normalize(second).content_hash


def test_extracts_contacts():
    raw = RawOpportunity(
        source="x",
        source_type="telegram",
        external_id="1",
        raw_text="Пишите @client_name или mail@example.com",
    )
    result = normalize(raw)
    assert result.contact_username == "@client_name"
    assert result.contact_email == "mail@example.com"


def test_does_not_treat_unrelated_mention_as_contact():
    raw = RawOpportunity(
        source="x",
        source_type="telegram",
        external_id="2",
        raw_text="Вакансия из канала @python_jobs. Отклик по ссылке.",
    )
    assert normalize(raw).contact_username is None


def test_normalize_unicode_and_spacing():
    assert normalize_text("  FASTAPI\n\tбот  ") == "fastapi бот"
