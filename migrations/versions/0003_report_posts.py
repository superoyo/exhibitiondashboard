"""report_posts table + report_kols.followers — refreshable report data

Revision ID: 0003_report_posts
Revises: 0002_report_kols
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_report_posts"
down_revision = "0002_report_kols"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "report_kols",
        sa.Column("followers", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_table(
        "report_posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("video_id", sa.String(length=64), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("cover_url", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("views", sa.BigInteger(), server_default="0"),
        sa.Column("likes", sa.BigInteger(), server_default="0"),
        sa.Column("comments", sa.BigInteger(), server_default="0"),
        sa.Column("shares", sa.BigInteger(), server_default="0"),
        sa.Column("saves", sa.BigInteger(), server_default="0"),
        sa.Column("scraped_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("video_id", name="uq_report_posts_video"),
    )
    op.create_index("ix_report_posts_username", "report_posts", ["username"])


def downgrade() -> None:
    op.drop_index("ix_report_posts_username", table_name="report_posts")
    op.drop_table("report_posts")
    op.drop_column("report_kols", "followers")
