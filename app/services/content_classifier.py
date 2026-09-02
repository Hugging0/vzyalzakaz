from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel, Field, model_validator

from app.config import AppSettings
from app.models import ClassificationMethod, ContentCategory
from app.schemas import RawOpportunity
from app.services.content_rules import CONTACT_ME_RE, FIRST_PERSON_IDENTITY_RE, PROFILE_LABEL_RE, RULES
from app.services.llm_client import ChatCompletionClient
from app.services.normalizer import normalize_text

logger = logging.getLogger(__name__)
CLASSIFICATION_VERSION = "intent-v1"
DEMAND_CATEGORIES = frozenset(
    {ContentCategory.PROJECT, ContentCategory.JOB, ContentCategory.GIG}
)
CATEGORY_PRIORITY = {
    ContentCategory.SPAM_OR_SCAM: 5,
    ContentCategory.AGENCY_OFFER: 4,
    ContentCategory.GIG: 3,
    ContentCategory.SERVICE_OFFER: 2,
    ContentCategory.JOB_SEEKER: 1,
    ContentCategory.PROJECT: 2,
    ContentCategory.JOB: 1,
}


def is_demand_category(category: ContentCategory | str | None) -> bool:
    try:
        return ContentCategory(category) in DEMAND_CATEGORIES
    except (TypeError, ValueError):
        return False


@dataclass(slots=True)
class DeterministicAssessment:
    category: ContentCategory
    confidence: float
    reasons: list[str] = field(default_factory=list)
    scores: dict[ContentCategory, float] = field(default_factory=dict)
    conflicting_sides: bool = False


@dataclass(slots=True)
class ContentClassification:
    category: ContentCategory
    confidence: float
    method: ClassificationMethod
    reasons: list[str]
    fallback_used: bool = False
    fallback_failed: bool = False
    latency_ms: float = 0
    version: str = CLASSIFICATION_VERSION

    @property
    def demand_side(self) -> bool:
        return is_demand_category(self.category)


def apply_classification_metadata(opportunity, classification: ContentClassification) -> None:
    """Persist the classifier result without coupling the classifier to SQLAlchemy sessions."""
    opportunity.content_category = classification.category
    opportunity.classification_confidence = classification.confidence
    opportunity.classification_method = classification.method
    opportunity.classification_reasons = classification.reasons
    opportunity.classification_fallback_used = classification.fallback_used
    opportunity.classification_fallback_failed = classification.fallback_failed
    opportunity.classification_latency_ms = classification.latency_ms
    opportunity.classification_version = classification.version


class SemanticIntentResult(BaseModel):
    category: ContentCategory
    demand_side: bool
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def validate_direction(self) -> SemanticIntentResult:
        if self.demand_side != is_demand_category(self.category):
            raise ValueError("category and demand_side disagree")
        return self


class SemanticIntentClassifier(Protocol):
    @property
    def available(self) -> bool: ...

    async def classify(
        self,
        raw: RawOpportunity,
        assessment: DeterministicAssessment,
    ) -> SemanticIntentResult: ...


class DeterministicContentClassifier:
    """Direction-aware local classifier based on weighted, explainable evidence."""

    def classify(self, raw: RawOpportunity) -> DeterministicAssessment:
        text = normalize_text(raw.raw_text or f"{raw.title} {raw.description}")
        scores: defaultdict[ContentCategory, float] = defaultdict(float)
        reasons: defaultdict[ContentCategory, list[str]] = defaultdict(list)

        for intent_rule in RULES:
            if intent_rule.pattern.search(text):
                scores[intent_rule.category] += intent_rule.weight
                reasons[intent_rule.category].append(intent_rule.code)

        self._add_resume_structure(text, scores, reasons)
        self._add_source_hint(raw, scores, reasons)
        if not scores:
            return DeterministicAssessment(
                category=ContentCategory.UNKNOWN,
                confidence=0,
                reasons=["heuristic:no_decisive_intent"],
            )

        ordered = sorted(
            scores.items(),
            key=lambda item: (item[1], CATEGORY_PRIORITY.get(item[0], 0)),
            reverse=True,
        )
        category, best_score = ordered[0]
        runner_score = ordered[1][1] if len(ordered) > 1 else 0
        demand_score = max((scores[item] for item in DEMAND_CATEGORIES), default=0)
        non_demand_score = max(
            (score for item, score in scores.items() if item not in DEMAND_CATEGORIES),
            default=0,
        )
        conflicting_sides = demand_score >= 5 and non_demand_score >= 5
        margin = max(0, best_score - runner_score)
        confidence = min(0.99, 0.55 + min(best_score, 10) * 0.045 + min(margin, 4) * 0.02)
        if conflicting_sides:
            confidence = min(confidence, 0.68)
        if best_score < 3:
            category = ContentCategory.UNKNOWN
            confidence = min(confidence, 0.55)
        selected_reasons = list(reasons.get(category, []))
        if conflicting_sides:
            selected_reasons.append("heuristic:conflicting_demand_supply")
        return DeterministicAssessment(
            category=category,
            confidence=round(confidence, 3),
            reasons=selected_reasons or ["heuristic:no_decisive_intent"],
            scores=dict(scores),
            conflicting_sides=conflicting_sides,
        )

    @staticmethod
    def _add_resume_structure(text, scores, reasons) -> None:
        identity = bool(FIRST_PERSON_IDENTITY_RE.search(text))
        profile_labels = len(set(match.group(0) for match in PROFILE_LABEL_RE.finditer(text)))
        if identity:
            scores[ContentCategory.RESUME] += 2.5
            reasons[ContentCategory.RESUME].append("resume_structure:first_person_role")
        if profile_labels >= 2:
            scores[ContentCategory.RESUME] += 4
            reasons[ContentCategory.RESUME].append("resume_structure:multiple_profile_links")
        elif identity and profile_labels == 1:
            scores[ContentCategory.RESUME] += 2.5
            reasons[ContentCategory.RESUME].append("resume_structure:owned_profile_link")
        if identity and CONTACT_ME_RE.search(text):
            scores[ContentCategory.SERVICE_OFFER] += 4
            reasons[ContentCategory.SERVICE_OFFER].append("provider_intent:first_person_contact")

    @staticmethod
    def _add_source_hint(raw, scores, reasons) -> None:
        if raw.metadata.get("source_content_policy") == "demand_only":
            scores[ContentCategory.JOB] += 6
            reasons[ContentCategory.JOB].append("source_hint:structured_demand_feed")


class LLMIntentClassifier:
    def __init__(self, settings: AppSettings, client: ChatCompletionClient | None = None):
        self.settings = settings
        self.client = client or ChatCompletionClient(settings)

    @property
    def available(self) -> bool:
        return self.settings.intent_classifier_enabled and self.client.available

    async def classify(
        self,
        raw: RawOpportunity,
        assessment: DeterministicAssessment,
    ) -> SemanticIntentResult:
        categories = ", ".join(category.value for category in ContentCategory)
        text = (raw.raw_text or raw.description or raw.title).strip()[:6000]
        result = await self.client.complete(
            f"""
Classify who is offering work in this message. Demand-side means a client or employer is
seeking someone for paid work. Supply-side means a candidate, freelancer, or agency is
seeking work or selling services. Technology relevance is irrelevant.

Allowed categories: {categories}.
Demand-side categories are only: project, job, gig. Unknown is never demand-side.

Direction examples:
- "Looking for a Python developer" = job, demand-side.
- "Python developer looking for work" = job_seeker, not demand-side.
- "Our agency is looking for a developer" = job, demand-side.
- "Our developer agency is looking for clients" = agency_offer, not demand-side.

Source type: {raw.source_type}
Source policy: {raw.metadata.get("source_content_policy", "mixed")}
Local evidence: category={assessment.category.value}, confidence={assessment.confidence},
reasons={assessment.reasons}

Title: {raw.title[:500]}
Message:
{text}

Return a JSON object with category, demand_side, confidence from 0 to 1, and one concise reason.
Prefer unknown when the direction cannot be established. Do not infer that a post is a job only
because it lists technologies, experience, a budget, CV, or portfolio.
""".strip(),
            system=(
                "You classify hiring intent in noisy multilingual job-channel messages. "
                "Be conservative: false demand-side classifications are more harmful than unknown."
            ),
            model=self.settings.intent_classifier_model,
            max_tokens=220,
            timeout_seconds=min(self.settings.llm_timeout_seconds, 20),
        )
        return SemanticIntentResult.model_validate(result)


class ContentClassifier:
    def __init__(
        self,
        settings: AppSettings,
        *,
        deterministic: DeterministicContentClassifier | None = None,
        semantic: SemanticIntentClassifier | None = None,
    ):
        self.settings = settings
        self.deterministic = deterministic or DeterministicContentClassifier()
        self.semantic = semantic or LLMIntentClassifier(settings)

    async def classify(self, raw: RawOpportunity) -> ContentClassification:
        started = time.perf_counter()
        assessment = self.deterministic.classify(raw)
        threshold = (
            self.settings.intent_deterministic_demand_confidence
            if is_demand_category(assessment.category)
            else self.settings.intent_deterministic_reject_confidence
        )
        if (
            assessment.category != ContentCategory.UNKNOWN
            and not assessment.conflicting_sides
            and assessment.confidence >= threshold
        ):
            return self._finish(
                started,
                category=assessment.category,
                confidence=assessment.confidence,
                method=ClassificationMethod.DETERMINISTIC,
                reasons=assessment.reasons,
            )

        if not self.semantic.available:
            return self._finish(
                started,
                category=ContentCategory.UNKNOWN,
                confidence=assessment.confidence,
                method=ClassificationMethod.DETERMINISTIC,
                reasons=[*assessment.reasons, "semantic:unavailable"],
            )

        try:
            semantic = await self.semantic.classify(raw, assessment)
            threshold = (
                self.settings.intent_semantic_demand_confidence
                if semantic.demand_side
                else self.settings.intent_semantic_reject_confidence
            )
            if semantic.category == ContentCategory.UNKNOWN or semantic.confidence < threshold:
                return self._finish(
                    started,
                    category=ContentCategory.UNKNOWN,
                    confidence=semantic.confidence,
                    method=ClassificationMethod.SEMANTIC,
                    reasons=[*assessment.reasons, "semantic:uncertain"],
                    fallback_used=True,
                )
            return self._finish(
                started,
                category=semantic.category,
                confidence=semantic.confidence,
                method=ClassificationMethod.SEMANTIC,
                reasons=[*assessment.reasons, f"semantic:{semantic.reason[:160]}"],
                fallback_used=True,
            )
        except Exception as exc:
            logger.warning(
                "content_semantic_fallback_failed source=%s external_id=%s error=%s",
                raw.source,
                raw.external_id,
                type(exc).__name__,
            )
            return self._finish(
                started,
                category=ContentCategory.UNKNOWN,
                confidence=assessment.confidence,
                method=ClassificationMethod.SEMANTIC,
                reasons=[*assessment.reasons, "semantic:failure"],
                fallback_used=True,
                fallback_failed=True,
            )

    @staticmethod
    def _finish(
        started: float,
        *,
        category: ContentCategory,
        confidence: float,
        method: ClassificationMethod,
        reasons: list[str],
        fallback_used: bool = False,
        fallback_failed: bool = False,
    ) -> ContentClassification:
        return ContentClassification(
            category=category,
            confidence=round(confidence, 3),
            method=method,
            reasons=list(dict.fromkeys(reasons))[:16],
            fallback_used=fallback_used,
            fallback_failed=fallback_failed,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )
