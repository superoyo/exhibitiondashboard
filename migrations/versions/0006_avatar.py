"""report_posts.avatar_url — KOL profile picture for the posts table

Revision ID: 0006_avatar
Revises: 0005_campaigns
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_avatar"
down_revision = "0005_campaigns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("report_posts", sa.Column("avatar_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("report_posts", "avatar_url")
