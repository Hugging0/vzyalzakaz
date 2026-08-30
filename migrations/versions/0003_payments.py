"""add payment records

Revision ID: 0003_payments
Revises: 0002
Create Date: 2026-08-31
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_payments"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("provider_payment_id", sa.String(length=100), nullable=True),
        sa.Column("plan_code", sa.String(length=50), nullable=False),
        sa.Column("amount_rub", sa.String(length=20), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "waiting_for_capture",
                "succeeded",
                "canceled",
                name="paymentstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("confirmation_url", sa.Text(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["telegram_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("provider_payment_id"),
    )
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_idempotency_key", "payments", ["idempotency_key"])
    op.create_index("ix_payments_provider_payment_id", "payments", ["provider_payment_id"])
    op.create_index("ix_payments_status", "payments", ["status"])


def downgrade() -> None:
    op.drop_table("payments")
