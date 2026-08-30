from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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
    fit_score: float | None
    money_score: float | None
    win_score: float | None
    freshness_score: float | None
    final_score: float | None
    estimated_effort_hours: float | None
    estimated_effective_hourly_rate: float | None
    analysis: dict
    proposal: str | None
    portfolio_item: str | None
    status: OpportunityStatus
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
