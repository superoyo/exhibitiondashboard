"""report_comments — the TEXT of comments under campaign posts, plus their
classification (category / sentiment / theme).

report_posts.comments only ever held a COUNT, so nothing in the product could
answer "what are people actually saying". This table is what the campaign
comment breakdown reads from.

comment_id carries the platform's own id and is unique: re-scraping a post
updates rows rather than duplicating them, matching how report_posts already
behaves.

Revision ID: 0016_comments
Revises: 0015_tiein
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_comments"
down_revision = "0015_tiein"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_comments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign", sa.String(length=32), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("post_video_id", sa.String(length=64), nullable=False),
        sa.Column("kol_username", sa.String(length=255), nullable=False),
        sa.Column("comment_id", sa.String(length=128), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("likes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_reply", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("category", sa.String(length=16), nullable=True),
        sa.Column("sentiment", sa.String(length=8), nullable=True),
        sa.Column("theme", sa.String(length=64), nullable=True),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("comment_id", name="uq_report_comments_comment_id"),
    )
    op.create_index("ix_report_comments_campaign", "report_comments", ["campaign"])
    op.create_index("ix_report_comments_platform", "report_comments", ["platform"])
    op.create_index("ix_report_comments_post_video_id", "report_comments", ["post_video_id"])
    op.create_index("ix_report_comments_kol_username", "report_comments", ["kol_username"])
    op.create_index("ix_report_comments_comment_id", "report_comments", ["comment_id"])
    op.create_index("ix_report_comments_category", "report_comments", ["category"])
    op.create_index("ix_report_comments_sentiment", "report_comments", ["sentiment"])


def downgrade() -> None:
    op.drop_table("report_comments")
