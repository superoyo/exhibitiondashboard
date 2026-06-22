"""app_settings key/value table — runtime-editable Apify token

Revision ID: 0004_app_settings
Revises: 0003_report_posts
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_app_settings"
down_revision = "0003_report_posts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
