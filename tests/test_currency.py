from datetime import UTC, date, datetime

import pytest

from app.models import ClassificationMethod, ContentCategory, Opportunity, TelegramUser
from app.schemas import RawOpportunity
from app.services.content_classifier import ContentClassification
from app.services.currency import FxRateQuote, parse_cbr_rates
from app.services.matching import UserMatchAnalyzer, deterministic_match
from app.services.opportunity_facts import OpportunityFactExtractor


class StaticFxProvider:
    name = "test"

    def __init__(self, rates: dict[str, float]):
        self.rates = rates

    async def get_rate(self, currency: str, on_date: date | None = None):
        rate = self.rates.get(currency)
        return FxRateQuote(currency, rate, on_date or date(2026, 9, 3), self.name) if rate else None


def classification() -> ContentClassification:
    return ContentClassification(
        category=ContentCategory.PROJECT,
        confidence=0.9,
        method=ClassificationMethod.DETERMINISTIC,
        reasons=["test"],
        version="test-v1",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("currency", "rate", "expected"),
    [("USD", 80.0, 80_000.0), ("EUR", 90.0, 90_000.0), ("RUB", 1.0, 1_000.0)],
)
async def test_fact_extraction_normalizes_currencies_without_network(
    settings, currency, rate, expected
):
    extractor = OpportunityFactExtractor(settings, StaticFxProvider({currency: rate}))
    raw = RawOpportunity(
        source="test",
        source_type="web",
        external_id=currency,
        title="Paid project",
        raw_text="Need a specialist",
        budget_max=1_000,
        currency=currency,
        published_at=datetime(2026, 9, 3, tzinfo=UTC),
    )

    facts = await extractor.extract(raw, classification(), allow_llm=False)

    assert facts.normalized_budget_max_rub == expected
    assert facts.fx_rate_to_rub == rate
    assert facts.fx_rate_date == date(2026, 9, 3)
    assert facts.fx_status == ("same_currency" if currency == "RUB" else "normalized")


@pytest.mark.asyncio
async def test_unknown_fx_never_hard_rejects_and_is_explained(settings, profile):
    facts = await OpportunityFactExtractor(settings, StaticFxProvider({})).extract(
        RawOpportunity(
            source="test",
            source_type="web",
            external_id="unknown-fx",
            title="Backend task",
            raw_text="Build backend service",
            budget_max=500,
            currency="XYZ",
        ),
        classification(),
        allow_llm=False,
    )
    opportunity = Opportunity(
        source="test",
        source_type="web",
        external_id="unknown-fx",
        title=facts.title,
        raw_text="Build backend service",
        normalized_hash="1" * 64,
        published_at=datetime.now(UTC),
    )
    user = TelegramUser(telegram_user_id=1, profile=profile.model_dump(), portfolio=[])
    analyzer = UserMatchAnalyzer(settings)

    eligibility = analyzer.cheap_eligibility(user, opportunity, facts, profile)
    analysis = deterministic_match(opportunity, facts, profile, [], retrieval_score=80)

    assert eligibility.passed
    assert facts.fx_status == "rate_unavailable"
    assert analysis.dimensions["money"].score == 50
    assert any("курс" in item.text.lower() for item in analysis.checks)


def test_cbr_parser_respects_nominal_and_effective_date():
    rates = parse_cbr_rates(
        b'<ValCurs Date="03.09.2026"><Valute><CharCode>USD</CharCode>'
        b'<Nominal>1</Nominal><Value>80,5000</Value></Valute>'
        b'<Valute><CharCode>JPY</CharCode><Nominal>100</Nominal>'
        b'<Value>55,0000</Value></Valute></ValCurs>'
    )

    assert rates["USD"].rate_to_rub == 80.5
    assert rates["JPY"].rate_to_rub == 0.55
    assert rates["USD"].effective_date == date(2026, 9, 3)
