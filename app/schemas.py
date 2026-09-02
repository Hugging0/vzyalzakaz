from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import OpportunityStatus


class RawOpportunity(BaseModel):
    source: str
    source_type: str
    external_id: str
    title: str = ""
    description: str = ""
    raw_text: str = ""
    source_url: str | None = None
    company: str | None = None
    client_name: str | None = None
    contact_username: str | None = None
    contact_email: str | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    currency: str | None = None
    employment_type: str | None = None
    estimated_hours: float | None = None
    remote: bool | None = None
    country: str | None = None
    languages: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
    edited_at: datetime | None = None
    apply_mode: str = "draft_only"
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMAnalysis(BaseModel):
    job_type: str = "unknown"
    summary: str = ""
    required_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    budget_quality: str = "unknown"
    estimated_hours: float = 0
    possible_with_vibe_coding: bool = False
    requires_daytime_presence: bool = False
    fit_reason: str = ""
    risks: list[str] = Field(default_factory=list)
    recommended_portfolio_project: str = ""
    fit_score: float = Field(ge=0, le=100)
    money_score: float = Field(ge=0, le=100)
    win_score: float = Field(ge=0, le=100)


class OpportunityFacts(BaseModel):
    """Candidate-independent facts extracted once from a global opportunity."""

    title: str = ""
    work_type: str = "unknown"
    category: str = "unknown"
    skills: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    seniority: str | None = None
    deliverables: list[str] = Field(default_factory=list)
    budget_raw: str | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    currency: str | None = None
    duration: str | None = None
    estimated_effort_min_hours: float | None = None
    estimated_effort_max_hours: float | None = None
    remote: bool | None = None
    time_zone_constraints: list[str] = Field(default_factory=list)
    meeting_constraints: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    client_facts: list[str] = Field(default_factory=list)
    competition_facts: list[str] = Field(default_factory=list)
    deadline: str | None = None
    contacts: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    source_confidence: float = Field(default=0, ge=0, le=1)
    evidence: dict[str, list[str]] = Field(default_factory=dict)


class MatchEvidence(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    source_facts: list[str] = Field(default_factory=list)
    profile_facts: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def has_provenance(self) -> MatchEvidence:
        if not self.source_facts and not self.profile_facts:
            raise ValueError("match explanation must reference a source or profile fact")
        return self


class MatchDimension(BaseModel):
    score: float = Field(ge=0, le=100)
    label: str
    source_facts: list[str] = Field(default_factory=list)
    profile_facts: list[str] = Field(default_factory=list)


class UserMatchAnalysis(BaseModel):
    """Explainable candidate-specific assessment derived from OpportunityFacts."""

    matched_capabilities: list[str] = Field(default_factory=list)
    missing_must_haves: list[str] = Field(default_factory=list)
    transferable_capabilities: list[str] = Field(default_factory=list)
    portfolio_evidence: list[str] = Field(default_factory=list)
    dimensions: dict[str, MatchDimension] = Field(default_factory=dict)
    risks: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    rank_score: float = Field(ge=0, le=100)
    strength_label: str
    why_recommended: list[MatchEvidence] = Field(default_factory=list)
    checks: list[MatchEvidence] = Field(default_factory=list)
    feature_vector: dict[str, float] = Field(default_factory=dict)
    reranked: bool = False
    ranking_version: str = "hybrid-v1"


class ProfileIntake(BaseModel):
    """Structured facts extracted from a free-form profile introduction."""

    skills: list[str] = Field(default_factory=list, max_length=40)
    specialties: list[str] = Field(default_factory=list, max_length=8)
    languages: list[str] = Field(default_factory=list, max_length=10)
    minimum_project_rub: int | None = Field(default=None, ge=0, le=100_000_000)
    target_hourly_rub: int | None = Field(default=None, ge=0, le=1_000_000)


class OpportunityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source: str
    source_type: str
    source_url: str | None
    title: str
    description: str
    company: str | None
    contact_username: str | None
    budget_min: float | None
    budget_max: float | None
    currency: str | None
    employment_type: str | None
    published_at: datetime | None
    collected_at: datetime
    facts: dict
    facts_version: str | None
    status: OpportunityStatus
    skip_reason: str | None
    apply_mode: str


class StatusUpdate(BaseModel):
    status: OpportunityStatus
    reason: str | None = None


class AnalyticsRead(BaseModel):
    users: int = 0
    active_users: int = 0
    personal_matches: int = 0
    scanned: int
    filtered: int
    recommended: int
    approved: int
    contacted: int
    replied: int
    interviews: int
    won: int
