"""promo_campaigns — Promotion Page Package overview.

Clients pre-buy posting quotas on Facebook promotion pages ("10 posts on page
X this year") and each team member tracks their deals in their own sheet. The
new /promotion-packages page answers "which deals still have quota left, how
many posts are used, and where are the posts" across all of them (team,
2026-11-17).

One table, because the page is read-only by decision: a row is a pointer to
the team member's sheet plus the last snapshot parsed from it (data_json,
replaced wholesale on every sync). The sheets stay the source of truth and
are never written to, so packs and slots get no tables of their own.

Revision ID: 0023_promo_campaigns
Revises: 0022_money_notes
Create Date: 2026-11-17
"""
import sqlalchemy as sa
from alembic import op

revision = "0023_promo_campaigns"
down_revision = "0022_money_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "promo_campaigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("team", sa.String(length=255), nullable=True),
        sa.Column("sheet_url", sa.Text(), nullable=False),
        sa.Column("data_json", sa.Text(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("promo_campaigns")
