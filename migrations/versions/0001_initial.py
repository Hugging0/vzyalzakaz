"""Initial JobHunter schema.

Revision ID: 0001
Revises:
"""

from alembic import op

from app.models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in (
        "opportunities",
        "source_occurrences",
        "collector_runs",
        "contact_logs",
    ):
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in (
        "contact_logs",
        "collector_runs",
        "source_occurrences",
        "opportunities",
    ):
        Base.metadata.tables[table_name].drop(bind=bind, checkfirst=True)
