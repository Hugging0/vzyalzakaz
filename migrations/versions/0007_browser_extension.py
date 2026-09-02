"""add browser extension sessions and command queue

Revision ID: 0007_browser_extension
Revises: 0006_content_classification
Create Date: 2026-09-02
"""

import sqlalchemy as sa
from alembic import op

from app.models import ApplicationCommandStatus

revision = "0007_browser_extension"
down_revision = "0006_content_classification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    command_status = sa.Enum(
        ApplicationCommandStatus,
        native_enum=False,
        values_callable=lambda enum: [item.value for item in enum],
    )
    op.create_table(
        "extension_link_tickets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["telegram_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_extension_link_tickets_user_id", "extension_link_tickets", ["user_id"])
    op.create_index(
        "ix_extension_link_tickets_code_hash",
        "extension_link_tickets",
        ["code_hash"],
        unique=True,
    )
    op.create_index(
        "ix_extension_link_tickets_expires_at",
        "extension_link_tickets",
        ["expires_at"],
    )

    op.create_table(
        "extension_installations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("installation_id", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("browser", sa.String(length=30), nullable=False),
        sa.Column("version", sa.String(length=30), nullable=False),
        sa.Column("active_source_id", sa.String(length=100)),
        sa.Column("marketplace_auth_state", sa.String(length=30)),
        sa.Column("last_error_code", sa.String(length=60)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["telegram_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "installation_id", name="uq_extension_user_installation"),
    )
    op.create_index("ix_extension_installations_user_id", "extension_installations", ["user_id"])
    op.create_index(
        "ix_extension_installations_token_hash",
        "extension_installations",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_extension_installations_expires_at",
        "extension_installations",
        ["expires_at"],
    )
    op.create_index(
        "ix_extension_installations_revoked_at",
        "extension_installations",
        ["revoked_at"],
    )
    op.create_index(
        "ix_extension_installations_last_seen_at",
        "extension_installations",
        ["last_seen_at"],
    )

    op.create_table(
        "application_commands",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("user_opportunity_id", sa.Integer(), nullable=False),
        sa.Column("claimed_installation_id", sa.Uuid()),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("job_url", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", command_status, nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=60)),
        sa.Column("error_detail", sa.String(length=255)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["claimed_installation_id"],
            ["extension_installations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["telegram_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_opportunity_id"],
            ["user_opportunities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_application_command_idempotency"),
    )
    op.create_index("ix_application_commands_user_id", "application_commands", ["user_id"])
    op.create_index(
        "ix_application_commands_user_opportunity_id",
        "application_commands",
        ["user_opportunity_id"],
    )
    op.create_index(
        "ix_application_commands_claimed_installation_id",
        "application_commands",
        ["claimed_installation_id"],
    )
    op.create_index("ix_application_commands_source_id", "application_commands", ["source_id"])
    op.create_index("ix_application_commands_status", "application_commands", ["status"])
    op.create_index("ix_application_commands_expires_at", "application_commands", ["expires_at"])
    op.create_index("ix_application_commands_created_at", "application_commands", ["created_at"])
    op.create_index(
        "ix_application_command_user_status",
        "application_commands",
        ["user_id", "status", "created_at"],
    )

    op.create_table(
        "extension_diagnostics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("command_id", sa.Uuid()),
        sa.Column("event", sa.String(length=60), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["command_id"], ["application_commands.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["installation_id"], ["extension_installations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["telegram_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_extension_diagnostics_user_id", "extension_diagnostics", ["user_id"])
    op.create_index(
        "ix_extension_diagnostics_installation_id",
        "extension_diagnostics",
        ["installation_id"],
    )
    op.create_index(
        "ix_extension_diagnostics_command_id", "extension_diagnostics", ["command_id"]
    )
    op.create_index("ix_extension_diagnostics_event", "extension_diagnostics", ["event"])
    op.create_index(
        "ix_extension_diagnostics_created_at", "extension_diagnostics", ["created_at"]
    )


def downgrade() -> None:
    op.drop_table("extension_diagnostics")
    op.drop_table("application_commands")
    op.drop_table("extension_installations")
    op.drop_table("extension_link_tickets")
