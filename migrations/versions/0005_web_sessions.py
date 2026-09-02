"""add web sessions and application history

Revision ID: 0005_web_sessions
Revises: 0004_country_text
Create Date: 2026-09-01
"""

from alembic import op

from app.models import ApplicationEvent, WebLoginTicket, WebSession

revision = "0005_web_sessions"
down_revision = "0004_country_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    ApplicationEvent.__table__.create(bind=bind, checkfirst=True)
    WebLoginTicket.__table__.create(bind=bind, checkfirst=True)
    WebSession.__table__.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    WebSession.__table__.drop(bind=bind, checkfirst=True)
    WebLoginTicket.__table__.drop(bind=bind, checkfirst=True)
    ApplicationEvent.__table__.drop(bind=bind, checkfirst=True)
