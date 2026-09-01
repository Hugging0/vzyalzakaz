"""allow long opportunity location lists

Revision ID: 0004_country_text
Revises: 0003_payments
Create Date: 2026-09-01
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_country_text"
down_revision = "0003_payments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "opportunities",
        "country",
        existing_type=sa.String(length=100),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "opportunities",
        "country",
        existing_type=sa.Text(),
        type_=sa.String(length=100),
        existing_nullable=True,
    )
