"""image_cache — cache remote image bytes so expiring TikTok CDN URLs don't
make KOL pictures disappear

Revision ID: 0009_image_cache
Revises: 0008_campaigns_meta
Create Date: 2027-07-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_image_cache"
down_revision = "0008_campaigns_meta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "image_cache",
        sa.Column("hash", sa.String(length=64), primary_key=True),
        sa.Column("content_type", sa.String(length=64), nullable=True),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("image_cache")
