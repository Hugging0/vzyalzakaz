"""add semantic cache and remove global personalization

Revision ID: 0009_semantic_retrieval
Revises: 0008_hybrid_recommendations
Create Date: 2026-09-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_semantic_retrieval"
down_revision = "0008_hybrid_recommendations"
branch_labels = None
depends_on = None

LEGACY_COLUMNS = (
    "prefilter_score",
    "prefilter_reasons",
    "fit_score",
    "money_score",
    "win_score",
    "freshness_score",
    "final_score",
    "estimated_effort_hours",
    "estimated_effective_hourly_rate",
    "analysis",
    "proposal",
    "portfolio_item",
    "notified_at",
    "approved_at",
    "sent_at",
)
LEGACY_USER_MATCH_COLUMNS = (
    "prefilter_score",
    "prefilter_reasons",
    "semantic_score",
    "fit_score",
    "money_score",
    "win_score",
    "freshness_score",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "semantic_representations" not in inspector.get_table_names():
        op.create_table(
            "semantic_representations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("entity_type", sa.String(length=30), nullable=False),
            sa.Column("entity_key", sa.String(length=80), nullable=False),
            sa.Column("input_hash", sa.String(length=64), nullable=False),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("model", sa.String(length=120), nullable=False),
            sa.Column("dimensions", sa.Integer(), nullable=False),
            sa.Column("vector", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "entity_type",
                "entity_key",
                "provider",
                "model",
                name="uq_semantic_representation_entity_provider_model",
            ),
        )
        op.create_index(
            "ix_semantic_representations_input_hash",
            "semantic_representations",
            ["input_hash"],
        )

    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("opportunities")}
    indexes = {index["name"] for index in inspector.get_indexes("opportunities")}
    with op.batch_alter_table("opportunities") as batch:
        for index in ("ix_opportunity_status_score", "ix_opportunities_final_score"):
            if index in indexes:
                batch.drop_index(index)
        for column in LEGACY_COLUMNS:
            if column in columns:
                batch.drop_column(column)
    match_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("user_opportunities")
    }
    with op.batch_alter_table("user_opportunities") as batch:
        for column in LEGACY_USER_MATCH_COLUMNS:
            if column in match_columns:
                batch.drop_column(column)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("opportunities")}
    additions = {
        "prefilter_score": sa.Column("prefilter_score", sa.Float()),
        "prefilter_reasons": sa.Column("prefilter_reasons", sa.JSON()),
        "fit_score": sa.Column("fit_score", sa.Float()),
        "money_score": sa.Column("money_score", sa.Float()),
        "win_score": sa.Column("win_score", sa.Float()),
        "freshness_score": sa.Column("freshness_score", sa.Float()),
        "final_score": sa.Column("final_score", sa.Float()),
        "estimated_effort_hours": sa.Column("estimated_effort_hours", sa.Float()),
        "estimated_effective_hourly_rate": sa.Column("estimated_effective_hourly_rate", sa.Float()),
        "analysis": sa.Column("analysis", sa.JSON()),
        "proposal": sa.Column("proposal", sa.Text()),
        "portfolio_item": sa.Column("portfolio_item", sa.String(length=100)),
        "notified_at": sa.Column("notified_at", sa.DateTime(timezone=True)),
        "approved_at": sa.Column("approved_at", sa.DateTime(timezone=True)),
        "sent_at": sa.Column("sent_at", sa.DateTime(timezone=True)),
    }
    with op.batch_alter_table("opportunities") as batch:
        for name, column in additions.items():
            if name not in columns:
                batch.add_column(column)
    op.create_index("ix_opportunities_final_score", "opportunities", ["final_score"])
    op.create_index(
        "ix_opportunity_status_score",
        "opportunities",
        ["status", "final_score"],
    )
    match_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("user_opportunities")
    }
    match_additions = {
        "prefilter_score": sa.Column("prefilter_score", sa.Float()),
        "prefilter_reasons": sa.Column("prefilter_reasons", sa.JSON()),
        "semantic_score": sa.Column("semantic_score", sa.Float()),
        "fit_score": sa.Column("fit_score", sa.Float()),
        "money_score": sa.Column("money_score", sa.Float()),
        "win_score": sa.Column("win_score", sa.Float()),
        "freshness_score": sa.Column("freshness_score", sa.Float()),
    }
    with op.batch_alter_table("user_opportunities") as batch:
        for name, column in match_additions.items():
            if name not in match_columns:
                batch.add_column(column)
    if "semantic_representations" in inspector.get_table_names():
        op.drop_table("semantic_representations")
