"""Persist Telegram catch-up positions independently of live events."""

import sqlalchemy as sa
from alembic import op

revision = "0010_collector_checkpoints"
down_revision = "0009_semantic_retrieval"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "collector_checkpoints",
        sa.Column("source", sa.String(100), primary_key=True),
        sa.Column("last_message_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("collector_checkpoints")
