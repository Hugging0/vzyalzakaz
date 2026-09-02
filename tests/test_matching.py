from datetime import UTC, datetime

from app.models import ContentCategory, Opportunity, TelegramUser
from app.schemas import OpportunityFacts
from app.services.matching import UserMatchAnalyzer, deterministic_match


def opportunity() -> Opportunity:
    return Opportunity(
        source="test",
        source_type="web",
        external_id="match-1",
        title="Backend API",
        description="Build a Django API",
        raw_text="Looking for a Django backend developer for a remote project",
        normalized_hash="f" * 64,
        content_category=ContentCategory.PROJECT,
        published_at=datetime.now(UTC),
    )


def facts(**updates) -> OpportunityFacts:
    values = {
        "title": "Backend API",
        "category": "project",
        "work_type": "project",
        "skills": ["Django"],
        "technologies": ["API"],
        "deliverables": ["Backend API"],
        "remote": True,
        "source_confidence": 0.9,
        "risk_flags": ["deadline_unclear", "client_unknown"],
    }
    values.update(updates)
    return OpportunityFacts.model_validate(values)


def test_hard_constraints_are_user_specific(settings, profile):
    matcher = UserMatchAnalyzer(settings)
    user = TelegramUser(telegram_user_id=1, profile=profile.model_dump(), portfolio=[])
    low_budget = facts(budget_max=1_000, currency="RUB")

    result = matcher.cheap_eligibility(user, opportunity(), low_budget, profile)

    assert not result.passed
    assert "budget_below_floor" in result.reasons


def test_semantic_transfer_does_not_require_exact_skill(profile):
    profile.candidate.skills = ["FastAPI"]

    analysis = deterministic_match(opportunity(), facts(), profile, [])

    assert not analysis.matched_capabilities
    assert analysis.transferable_capabilities
    assert analysis.feature_vector["semantic_similarity"] > 0
    assert analysis.rank_score > 0


def test_explanations_reference_source_or_profile_facts(profile):
    profile.candidate.skills = ["Django", "API"]

    analysis = deterministic_match(opportunity(), facts(), profile, [])

    assert analysis.why_recommended
    assert analysis.checks
    for item in [*analysis.why_recommended, *analysis.checks]:
        assert item.source_facts or item.profile_facts
