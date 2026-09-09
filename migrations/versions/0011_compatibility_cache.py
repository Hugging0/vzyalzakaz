"""Cache evidence-based compatibility per profile and source revision."""

import sqlalchemy as sa
from alembic import op

revision = "0011_compatibility_cache"
down_revision = "0010_collector_checkpoints"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "compatibility_cache",
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("telegram_users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "opportunity_id",
            sa.Uuid(),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("decision", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("compatibility_cache")
