"""initial schema: kols, scrape_runs, posts, post_metrics, kol_daily

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kols",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("display", sa.String(length=255), nullable=False),
        sa.Column("content_group", sa.String(length=64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("username", name="uq_kols_username"),
    )
    op.create_index("ix_kols_username", "kols", ["username"])

    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("apify_run_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("posts_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(10, 4), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_scrape_runs_run_date", "scrape_runs", ["run_date"])

    op.create_table(
        "posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kol_id", sa.Integer(), sa.ForeignKey("kols.id"), nullable=False),
        sa.Column("video_id", sa.String(length=64), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_pinned", sa.Boolean(), server_default=sa.false()),
        sa.Column("is_slideshow", sa.Boolean(), server_default=sa.false()),
        sa.Column("first_seen", sa.Date(), nullable=False),
        sa.Column("last_scraped", sa.Date(), nullable=False),
        sa.UniqueConstraint("video_id", name="uq_posts_video_id"),
    )
    op.create_index("ix_posts_kol_id", "posts", ["kol_id"])
    op.create_index("ix_posts_video_id", "posts", ["video_id"])

    op.create_table(
        "post_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("post_id", sa.Integer(), sa.ForeignKey("posts.id"), nullable=False),
        sa.Column("scrape_date", sa.Date(), nullable=False),
        sa.Column("views", sa.BigInteger(), server_default="0"),
        sa.Column("likes", sa.BigInteger(), server_default="0"),
        sa.Column("comments", sa.BigInteger(), server_default="0"),
        sa.Column("shares", sa.BigInteger(), server_default="0"),
        sa.Column("saves", sa.BigInteger(), server_default="0"),
        sa.UniqueConstraint("post_id", "scrape_date", name="uq_post_metric_day"),
    )
    op.create_index("ix_post_metrics_post_id", "post_metrics", ["post_id"])
    op.create_index("ix_post_metrics_scrape_date", "post_metrics", ["scrape_date"])

    op.create_table(
        "kol_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kol_id", sa.Integer(), sa.ForeignKey("kols.id"), nullable=False),
        sa.Column("scrape_date", sa.Date(), nullable=False),
        sa.Column("followers", sa.BigInteger(), server_default="0"),
        sa.Column("posts_7d", sa.Integer(), server_default="0"),
        sa.Column("views_7d", sa.BigInteger(), server_default="0"),
        sa.Column("likes_7d", sa.BigInteger(), server_default="0"),
        sa.Column("comments_7d", sa.BigInteger(), server_default="0"),
        sa.Column("shares_7d", sa.BigInteger(), server_default="0"),
        sa.Column("saves_7d", sa.BigInteger(), server_default="0"),
        sa.Column("engagement_rate", sa.Numeric(8, 5), nullable=True),
        sa.UniqueConstraint("kol_id", "scrape_date", name="uq_kol_daily_day"),
    )
    op.create_index("ix_kol_daily_kol_id", "kol_daily", ["kol_id"])
    op.create_index("ix_kol_daily_scrape_date", "kol_daily", ["scrape_date"])


def downgrade() -> None:
    op.drop_table("kol_daily")
    op.drop_table("post_metrics")
    op.drop_table("posts")
    op.drop_table("scrape_runs")
    op.drop_table("kols")
