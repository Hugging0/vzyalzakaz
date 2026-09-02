"""add content intent classification metadata

Revision ID: 0006_content_classification
Revises: 0005_web_sessions
Create Date: 2026-09-02
"""

import sqlalchemy as sa
from alembic import op

from app.models import ClassificationMethod, ContentCategory

revision = "0006_content_classification"
down_revision = "0005_web_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    opportunity_columns = {column["name"] for column in inspector.get_columns("opportunities")}
    collector_columns = {column["name"] for column in inspector.get_columns("collector_runs")}
    content_category = sa.Enum(
        ContentCategory,
        native_enum=False,
        values_callable=lambda enum: [item.value for item in enum],
    )
    classification_method = sa.Enum(
        ClassificationMethod,
        native_enum=False,
        values_callable=lambda enum: [item.value for item in enum],
    )
    opportunity_additions = {
        "content_category": sa.Column(
            "content_category",
            content_category,
            nullable=False,
            server_default=ContentCategory.UNKNOWN.value,
        ),
        "classification_confidence": sa.Column("classification_confidence", sa.Float()),
        "classification_method": sa.Column("classification_method", classification_method),
        "classification_reasons": sa.Column(
            "classification_reasons",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        "classification_fallback_used": sa.Column(
            "classification_fallback_used",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        "classification_fallback_failed": sa.Column(
            "classification_fallback_failed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        "classification_latency_ms": sa.Column("classification_latency_ms", sa.Float()),
        "classification_version": sa.Column("classification_version", sa.String(length=30)),
    }
    for name, column in opportunity_additions.items():
        if name not in opportunity_columns:
            op.add_column("opportunities", column)
    indexes = {index["name"] for index in inspector.get_indexes("opportunities")}
    if "ix_opportunities_content_category" not in indexes:
        op.create_index(
            "ix_opportunities_content_category",
            "opportunities",
            ["content_category"],
        )

    collector_additions = {
        "classification_counts": sa.Column(
            "classification_counts",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        "semantic_fallback_count": sa.Column(
            "semantic_fallback_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        "semantic_fallback_failures": sa.Column(
            "semantic_fallback_failures",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        "classification_latency_ms": sa.Column(
            "classification_latency_ms",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    }
    for name, column in collector_additions.items():
        if name not in collector_columns:
            op.add_column("collector_runs", column)


def downgrade() -> None:
    op.drop_column("collector_runs", "classification_latency_ms")
    op.drop_column("collector_runs", "semantic_fallback_failures")
    op.drop_column("collector_runs", "semantic_fallback_count")
    op.drop_column("collector_runs", "classification_counts")

    op.drop_index("ix_opportunities_content_category", table_name="opportunities")
    op.drop_column("opportunities", "classification_version")
    op.drop_column("opportunities", "classification_latency_ms")
    op.drop_column("opportunities", "classification_fallback_failed")
    op.drop_column("opportunities", "classification_fallback_used")
    op.drop_column("opportunities", "classification_reasons")
    op.drop_column("opportunities", "classification_method")
    op.drop_column("opportunities", "classification_confidence")
    op.drop_column("opportunities", "content_category")
