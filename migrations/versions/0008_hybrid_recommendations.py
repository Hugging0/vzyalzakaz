"""separate global facts from personalized matching

Revision ID: 0008_hybrid_recommendations
Revises: 0007_browser_extension
Create Date: 2026-09-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_hybrid_recommendations"
down_revision = "0007_browser_extension"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    opportunity_columns = {column["name"] for column in inspector.get_columns("opportunities")}
    match_columns = {column["name"] for column in inspector.get_columns("user_opportunities")}
    opportunity_additions = {
        "facts": sa.Column(
            "facts", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
        ),
        "facts_version": sa.Column("facts_version", sa.String(length=30)),
    }
    match_additions = {
        "eligibility_reasons": sa.Column(
            "eligibility_reasons",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        "semantic_score": sa.Column(
            "semantic_score", sa.Float(), nullable=False, server_default="0"
        ),
        "feature_vector": sa.Column(
            "feature_vector", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
        ),
        "explanation": sa.Column(
            "explanation", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
        ),
        "match_confidence": sa.Column(
            "match_confidence", sa.Float(), nullable=False, server_default="0"
        ),
        "reranked": sa.Column(
            "reranked", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        "ranking_version": sa.Column(
            "ranking_version",
            sa.String(length=30),
            nullable=False,
            server_default="hybrid-v1",
        ),
    }
    for name, column in opportunity_additions.items():
        if name not in opportunity_columns:
            op.add_column("opportunities", column)
    for name, column in match_additions.items():
        if name not in match_columns:
            op.add_column("user_opportunities", column)

    # Global rows may contain the original owner's profile-derived values. Remove them.
    op.execute(
        """
        UPDATE opportunities
        SET prefilter_score = NULL,
            prefilter_reasons = '[]',
            fit_score = NULL,
            money_score = NULL,
            win_score = NULL,
            freshness_score = NULL,
            final_score = NULL,
            estimated_effort_hours = NULL,
            estimated_effective_hourly_rate = NULL,
            analysis = '{}',
            proposal = NULL,
            portfolio_item = NULL
        """
    )
    op.execute(
        """
        UPDATE opportunities
        SET status = 'NEW'
        WHERE content_category IN ('project', 'job', 'gig', 'unknown')
          AND status IN ('FILTERED', 'RECOMMENDED')
        """
    )


def downgrade() -> None:
    op.drop_column("user_opportunities", "ranking_version")
    op.drop_column("user_opportunities", "reranked")
    op.drop_column("user_opportunities", "match_confidence")
    op.drop_column("user_opportunities", "explanation")
    op.drop_column("user_opportunities", "feature_vector")
    op.drop_column("user_opportunities", "semantic_score")
    op.drop_column("user_opportunities", "eligibility_reasons")
    op.drop_column("opportunities", "facts_version")
    op.drop_column("opportunities", "facts")
