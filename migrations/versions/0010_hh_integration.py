"""add HH connections and application attempts

Revision ID: 0010_hh_integration
Revises: 0009_semantic_retrieval
Create Date: 2026-09-04
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_hh_integration"
down_revision = "0009_semantic_retrieval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("opportunities")}
    if "provider_metadata" not in columns:
        op.add_column(
            "opportunities",
            sa.Column("provider_metadata", sa.JSON(), nullable=False, server_default="{}"),
        )
    if "source_checked_at" not in columns:
        op.add_column(
            "opportunities",
            sa.Column(
                "source_checked_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )
    if "external_ai_allowed" not in columns:
        op.add_column(
            "opportunities",
            sa.Column("external_ai_allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    op.execute(sa.text("UPDATE opportunities SET external_ai_allowed = false WHERE source = 'hh_ru'"))
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("opportunities")}
    if "ix_opportunities_source_checked_at" not in indexes:
        op.create_index("ix_opportunities_source_checked_at", "opportunities", ["source_checked_at"])

    tables = set(sa.inspect(bind).get_table_names())
    if "external_connections" not in tables:
        _create_external_connections()
    if "oauth_states" not in tables:
        _create_oauth_states()
    if "integration_audit_events" not in tables:
        _create_integration_audit_events()
    if "application_attempts" not in tables:
        _create_application_attempts()


def _create_external_connections() -> None:
    op.create_table(
        "external_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("telegram_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("external_user_id", sa.String(length=100)),
        sa.Column("access_token_encrypted", sa.Text()),
        sa.Column("refresh_token_encrypted", sa.Text()),
        sa.Column("token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("selected_resume_id", sa.String(length=100)),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("last_error_code", sa.String(length=60)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "provider", name="uq_external_connection_user_provider"),
    )
    op.create_index("ix_external_connections_user_id", "external_connections", ["user_id"])
    op.create_index("ix_external_connections_provider", "external_connections", ["provider"])
    op.create_index("ix_external_connections_status", "external_connections", ["status"])


def _create_oauth_states() -> None:
    op.create_table(
        "oauth_states",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("telegram_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_oauth_states_user_id", "oauth_states", ["user_id"])
    op.create_index("ix_oauth_states_provider", "oauth_states", ["provider"])
    op.create_index("ix_oauth_states_state_hash", "oauth_states", ["state_hash"], unique=True)
    op.create_index("ix_oauth_states_expires_at", "oauth_states", ["expires_at"])


def _create_integration_audit_events() -> None:
    op.create_table(
        "integration_audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("telegram_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("event", sa.String(length=60), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_integration_audit_events_user_id", "integration_audit_events", ["user_id"])
    op.create_index("ix_integration_audit_events_provider", "integration_audit_events", ["provider"])
    op.create_index("ix_integration_audit_events_event", "integration_audit_events", ["event"])
    op.create_index("ix_integration_audit_events_created_at", "integration_audit_events", ["created_at"])


def _create_application_attempts() -> None:
    op.create_table(
        "application_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("telegram_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_opportunity_id",
            sa.Integer(),
            sa.ForeignKey("user_opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("external_id", sa.String(length=120)),
        sa.Column("error_code", sa.String(length=60)),
        sa.Column("detail", sa.String(length=255)),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_application_attempt_idempotency"),
        sa.UniqueConstraint(
            "user_id",
            "user_opportunity_id",
            "provider",
            name="uq_application_attempt_match_provider",
        ),
    )
    op.create_index("ix_application_attempts_user_id", "application_attempts", ["user_id"])
    op.create_index(
        "ix_application_attempts_user_opportunity_id",
        "application_attempts",
        ["user_opportunity_id"],
    )
    op.create_index("ix_application_attempts_provider", "application_attempts", ["provider"])
    op.create_index("ix_application_attempts_status", "application_attempts", ["status"])
    op.create_index("ix_application_attempts_created_at", "application_attempts", ["created_at"])
    op.create_index(
        "ix_application_attempt_user_opportunity_provider",
        "application_attempts",
        ["user_id", "user_opportunity_id", "provider"],
    )


def downgrade() -> None:
    op.drop_table("application_attempts")
    op.drop_table("integration_audit_events")
    op.drop_table("oauth_states")
    op.drop_table("external_connections")
    op.drop_index("ix_opportunities_source_checked_at", table_name="opportunities")
    with op.batch_alter_table("opportunities") as batch:
        batch.drop_column("external_ai_allowed")
        batch.drop_column("source_checked_at")
        batch.drop_column("provider_metadata")
