"""report_kols.avatar_url — channel profile picture (fetched from profile)

Revision ID: 0007_roster_avatar
Revises: 0006_avatar
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_roster_avatar"
down_revision = "0006_avatar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("report_kols", sa.Column("avatar_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("report_kols", "avatar_url")
