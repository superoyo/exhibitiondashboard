"""multi-platform: report_kols.links_json + report_posts.platform

A KOL can post the same campaign work on several platforms (TikTok, Facebook,
Instagram, YouTube, X, ...). links_json holds all of them; report_posts.platform
tags which platform a scraped post belongs to so stats stay separated.

Revision ID: 0010_multiplatform
Revises: 0009_image_cache
Create Date: 2027-07-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_multiplatform"
down_revision = "0009_image_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("report_kols", sa.Column("links_json", sa.Text(), nullable=True))
    op.add_column("report_posts", sa.Column("platform", sa.String(length=16),
                                            nullable=False, server_default="tiktok"))


def downgrade() -> None:
    op.drop_column("report_posts", "platform")
    op.drop_column("report_kols", "links_json")
