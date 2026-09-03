from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid


class Base(DeclarativeBase):
    pass


class OpportunityStatus(StrEnum):
    NEW = "new"
    FILTERED = "filtered"
    RECOMMENDED = "recommended"
    APPROVED = "approved"
    SKIPPED = "skipped"
    CONTACTED = "contacted"
    REPLIED = "replied"
    INTERVIEW = "interview"
    WON = "won"
    LOST = "lost"


class ContentCategory(StrEnum):
    PROJECT = "project"
    JOB = "job"
    GIG = "gig"
    RESUME = "resume"
    JOB_SEEKER = "job_seeker"
    SERVICE_OFFER = "service_offer"
    AGENCY_OFFER = "agency_offer"
    SELF_PROMOTION = "self_promotion"
    COURSE_OR_EDUCATION = "course_or_education"
    ADVERTISEMENT = "advertisement"
    COMMUNITY_POST = "community_post"
    EVENT = "event"
    SPAM_OR_SCAM = "spam_or_scam"
    UNKNOWN = "unknown"


class ClassificationMethod(StrEnum):
    DETERMINISTIC = "deterministic"
    SEMANTIC = "semantic"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    WAITING_FOR_CAPTURE = "waiting_for_capture"
    SUCCEEDED = "succeeded"
    CANCELED = "canceled"


class ApplicationCommandStatus(StrEnum):
    QUEUED = "queued"
    DELIVERED = "delivered"
    OPENING_PAGE = "opening_page"
    WAITING_FOR_AUTH = "waiting_for_auth"
    PAGE_READY = "page_ready"
    FORM_FOUND = "form_found"
    FILLING = "filling"
    PARTIALLY_FILLED = "partially_filled"
    READY_FOR_REVIEW = "ready_for_review"
    SUBMITTED = "submitted"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source: Mapped[str] = mapped_column(String(100), index=True)
    source_type: Mapped[str] = mapped_column(String(30))
    source_url: Mapped[str | None] = mapped_column(Text)
    external_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    company: Mapped[str | None] = mapped_column(String(255))
    client_name: Mapped[str | None] = mapped_column(String(255))
    contact_username: Mapped[str | None] = mapped_column(String(100))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    budget_min: Mapped[float | None] = mapped_column(Float)
    budget_max: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(10))
    employment_type: Mapped[str | None] = mapped_column(String(50))
    estimated_hours: Mapped[float | None] = mapped_column(Float)
    remote: Mapped[bool | None] = mapped_column(Boolean)
    country: Mapped[str | None] = mapped_column(Text)
    languages: Mapped[list] = mapped_column(JSON, default=list)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    technologies: Mapped[list] = mapped_column(JSON, default=list)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_text: Mapped[str] = mapped_column(Text)
    normalized_hash: Mapped[str] = mapped_column(String(64), index=True)
    content_category: Mapped[ContentCategory] = mapped_column(
        Enum(
            ContentCategory,
            native_enum=False,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=ContentCategory.UNKNOWN,
        index=True,
    )
    classification_confidence: Mapped[float | None] = mapped_column(Float)
    classification_method: Mapped[ClassificationMethod | None] = mapped_column(
        Enum(
            ClassificationMethod,
            native_enum=False,
            values_callable=lambda enum: [item.value for item in enum],
        ),
    )
    classification_reasons: Mapped[list] = mapped_column(JSON, default=list)
    classification_fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)
    classification_fallback_failed: Mapped[bool] = mapped_column(Boolean, default=False)
    classification_latency_ms: Mapped[float | None] = mapped_column(Float)
    classification_version: Mapped[str | None] = mapped_column(String(30))
    facts: Mapped[dict] = mapped_column(JSON, default=dict)
    facts_version: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[OpportunityStatus] = mapped_column(
        Enum(OpportunityStatus, native_enum=False), default=OpportunityStatus.NEW, index=True
    )
    skip_reason: Mapped[str | None] = mapped_column(String(100))
    apply_mode: Mapped[str] = mapped_column(String(30), default="draft_only")

    occurrences: Mapped[list[SourceOccurrence]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )
    user_matches: Mapped[list[UserOpportunity]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_opportunity_source_external"),
    )


class SourceOccurrence(Base):
    __tablename__ = "source_occurrences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(100))
    external_id: Mapped[str] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(Text)
    found_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    opportunity: Mapped[Opportunity] = relationship(back_populates="occurrences")

    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_occurrence_source_external"),)


class CollectorRun(Base):
    __tablename__ = "collector_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(100), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[int] = mapped_column(Integer, default=0)
    merged: Mapped[int] = mapped_column(Integer, default=0)
    classification_counts: Mapped[dict] = mapped_column(JSON, default=dict)
    semantic_fallback_count: Mapped[int] = mapped_column(Integer, default=0)
    semantic_fallback_failures: Mapped[int] = mapped_column(Integer, default=0)
    classification_latency_ms: Mapped[float] = mapped_column(Float, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class ContactLog(Base):
    __tablename__ = "contact_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("opportunities.id"), index=True)
    contact: Mapped[str] = mapped_column(String(255))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (UniqueConstraint("opportunity_id", "contact", name="uq_contact_opportunity_contact"),)


class TelegramUser(Base):
    __tablename__ = "telegram_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(100))
    first_name: Mapped[str | None] = mapped_column(String(255))
    language_code: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    profile: Mapped[dict] = mapped_column(JSON)
    portfolio: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    matches: Mapped[list[UserOpportunity]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserOpportunity(Base):
    __tablename__ = "user_opportunities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("telegram_users.id", ondelete="CASCADE"), index=True
    )
    opportunity_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    eligibility_reasons: Mapped[list] = mapped_column(JSON, default=list)
    final_score: Mapped[float] = mapped_column(Float, default=0, index=True)
    estimated_effort_hours: Mapped[float | None] = mapped_column(Float)
    estimated_effective_hourly_rate: Mapped[float | None] = mapped_column(Float)
    analysis: Mapped[dict] = mapped_column(JSON, default=dict)
    feature_vector: Mapped[dict] = mapped_column(JSON, default=dict)
    explanation: Mapped[dict] = mapped_column(JSON, default=dict)
    match_confidence: Mapped[float] = mapped_column(Float, default=0)
    reranked: Mapped[bool] = mapped_column(Boolean, default=False)
    ranking_version: Mapped[str] = mapped_column(String(30), default="hybrid-v2")
    proposal: Mapped[str | None] = mapped_column(Text)
    portfolio_item: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[OpportunityStatus] = mapped_column(
        Enum(OpportunityStatus, native_enum=False),
        default=OpportunityStatus.RECOMMENDED,
        index=True,
    )
    skip_reason: Mapped[str | None] = mapped_column(String(100))
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    user: Mapped[TelegramUser] = relationship(back_populates="matches")
    opportunity: Mapped[Opportunity] = relationship(back_populates="user_matches")

    __table_args__ = (
        UniqueConstraint("user_id", "opportunity_id", name="uq_user_opportunity"),
        Index("ix_user_opportunity_status_score", "user_id", "status", "final_score"),
    )


class SemanticRepresentation(Base):
    __tablename__ = "semantic_representations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_key: Mapped[str] = mapped_column(String(80))
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(120))
    dimensions: Mapped[int] = mapped_column(Integer)
    vector: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "entity_key",
            "provider",
            "model",
            name="uq_semantic_representation_entity_provider_model",
        ),
    )


class ApplicationEvent(Base):
    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_opportunities.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("telegram_users.id", ondelete="CASCADE"), index=True
    )
    event: Mapped[str] = mapped_column(String(50), index=True)
    detail: Mapped[str | None] = mapped_column(String(255))
    actor: Mapped[str] = mapped_column(String(30), default="web")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class WebLoginTicket(Base):
    __tablename__ = "web_login_tickets"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("telegram_users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class WebSession(Base):
    __tablename__ = "web_sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("telegram_users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ExtensionLinkTicket(Base):
    __tablename__ = "extension_link_tickets"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("telegram_users.id", ondelete="CASCADE"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ExtensionInstallation(Base):
    __tablename__ = "extension_installations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("telegram_users.id", ondelete="CASCADE"), index=True
    )
    installation_id: Mapped[str] = mapped_column(String(64))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    browser: Mapped[str] = mapped_column(String(30), default="chromium")
    version: Mapped[str] = mapped_column(String(30))
    active_source_id: Mapped[str | None] = mapped_column(String(100))
    marketplace_auth_state: Mapped[str | None] = mapped_column(String(30))
    last_error_code: Mapped[str | None] = mapped_column(String(60))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )

    __table_args__ = (
        UniqueConstraint("user_id", "installation_id", name="uq_extension_user_installation"),
    )


class ApplicationCommand(Base):
    __tablename__ = "application_commands"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("telegram_users.id", ondelete="CASCADE"), index=True
    )
    user_opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_opportunities.id", ondelete="CASCADE"), index=True
    )
    claimed_installation_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("extension_installations.id", ondelete="SET NULL"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(100))
    source_id: Mapped[str] = mapped_column(String(100), index=True)
    job_url: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[ApplicationCommandStatus] = mapped_column(
        Enum(
            ApplicationCommandStatus,
            native_enum=False,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=ApplicationCommandStatus.QUEUED,
        index=True,
    )
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(60))
    error_detail: Mapped[str | None] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_application_command_idempotency"),
        Index("ix_application_command_user_status", "user_id", "status", "created_at"),
    )


class ExtensionDiagnostic(Base):
    __tablename__ = "extension_diagnostics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("telegram_users.id", ondelete="CASCADE"), index=True
    )
    installation_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("extension_installations.id", ondelete="CASCADE"), index=True
    )
    command_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("application_commands.id", ondelete="CASCADE"), index=True
    )
    event: Mapped[str] = mapped_column(String(60), index=True)
    level: Mapped[str] = mapped_column(String(20), default="info")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("telegram_users.id", ondelete="CASCADE"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    plan_code: Mapped[str] = mapped_column(String(50))
    amount_rub: Mapped[str] = mapped_column(String(20))
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, native_enum=False), default=PaymentStatus.PENDING, index=True
    )
    confirmation_url: Mapped[str | None] = mapped_column(Text)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
