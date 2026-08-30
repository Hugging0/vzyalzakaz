"""Add isolated Telegram users and personal opportunity matches.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

from app.models import TelegramUser, UserOpportunity

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    TelegramUser.__table__.create(bind=bind, checkfirst=True)
    UserOpportunity.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    UserOpportunity.__table__.drop(bind=bind, checkfirst=True)
    TelegramUser.__table__.drop(bind=bind, checkfirst=True)
