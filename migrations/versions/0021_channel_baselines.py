"""channel_baselines — a channel's natural form, cached 30 days.

The Performance Analysis could only compare a post against the sold KPI, the
campaign median, and the KOL's past jobs in OUR system. The team wants the
comparison clients actually ask for — "ช่องนี้ปกติได้เท่าไหร่" — which needs the
channel's own recent ORGANIC posts. This table stores that as medians over the
latest ~10 posts per (username, platform), fetched from the channel page via
the same Apify actors the report already uses, and cached for 30 days so a KOL
appearing in several campaigns is paid for once.

Global across campaigns on purpose (no campaign column): the channel is the
same channel wherever it appears. Sponsored posts we track are excluded from
the sample at fetch time so a campaign post never inflates its own baseline.

Revision ID: 0021_channel_baselines
Revises: 0020_kpi_list
Create Date: 2026-09-02
"""
import sqlalchemy as sa
from alembic import op

revision = "0021_channel_baselines"
down_revision = "0020_kpi_list"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_baselines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=255), nullable=False, index=True),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("median_views", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("median_engagement", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("median_er_pct", sa.Float(), nullable=True),
        sa.UniqueConstraint("username", "platform",
                            name="uq_channel_baselines_user_platform"),
    )


def downgrade() -> None:
    op.drop_table("channel_baselines")
