from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.models import ContentCategory, Opportunity, TelegramUser
from app.schemas import OpportunityFacts
from app.services.matching import RANKING_POLICY, RerankResult, UserMatchAnalyzer, deterministic_match


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
    assert analysis.feature_vector["semantic_retrieval"] > 0
    assert analysis.rank_score > 0


def test_explanations_reference_source_or_profile_facts(profile):
    profile.candidate.skills = ["Django", "API"]

    analysis = deterministic_match(opportunity(), facts(), profile, [])

    assert analysis.why_recommended
    assert analysis.checks
    for item in [*analysis.why_recommended, *analysis.checks]:
        assert item.source_facts or item.profile_facts


def test_ranking_policy_is_versioned_and_normalized():
    assert RANKING_POLICY.version == "hybrid-v2"
    assert sum(RANKING_POLICY.weights.values()) == pytest.approx(1)


def test_llm_rerank_adjustment_is_bounded():
    with pytest.raises(ValueError):
        RerankResult(score_adjustment=9, confidence=0.8)


def test_video_adjacent_experience_does_not_require_same_software(profile):
    profile.candidate.skills = ["After Effects", "motion graphics"]
    video_facts = facts(
        title="Short product video",
        skills=["DaVinci Resolve"],
        technologies=[],
        deliverables=["Монтаж динамичного видео для reels"],
    )

    analysis = deterministic_match(opportunity(), video_facts, profile, [], retrieval_score=82)

    assert not analysis.matched_capabilities
    assert analysis.transferable_capabilities == ["video — смежный опыт"]
    assert analysis.rank_score > 0


@pytest.mark.asyncio
async def test_llm_rerank_outage_keeps_deterministic_analysis(settings, profile):
    configured = settings.model_copy(
        update={
            "llm_provider": "deepseek",
            "llm_api_key": "test",
            "matching_llm_rerank_threshold": 0,
        }
    )
    analyzer = UserMatchAnalyzer(configured)
    analyzer.client.complete = AsyncMock(side_effect=RuntimeError("provider outage"))
    profile.candidate.skills = ["Django", "API"]

    analysis = await analyzer.analyze(
        opportunity(),
        facts(),
        profile,
        [],
        retrieval_score=95,
        retrieval_fallback_used=False,
    )

    assert not analysis.reranked
    assert analysis.rank_score > 0
