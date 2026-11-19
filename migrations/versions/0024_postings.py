"""report_kols.postings_json — one account, several sold postings.

A promotion page is often bought for several posts in one campaign ("ปันโปร
โพสต์ที่ 7 for Falles, โพสต์ที่ 8 for Q'Lean"), one sheet row each. The import
merged those rows into one KOL and the report then showed the page's
best-performing post on every row of the block — the second posting's own
numbers never appeared, and its boost budget was dropped (team, 2026-11-19).

The account stays ONE roster row (it is one identity: one avatar, one
follower count, one entry in the KOL directory), and this column records the
postings inside it: JSON list of {"slot","label","cost_thb","boost_thb",
"cost_note","boost_note","kpis"}, null for the usual one-row account. Each
link in links_json carries its posting's "slot".

Revision ID: 0024_postings
Revises: 0023_promo_campaigns
Create Date: 2026-11-19
"""
import sqlalchemy as sa
from alembic import op

revision = "0024_postings"
down_revision = "0023_promo_campaigns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("report_kols", sa.Column("postings_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("report_kols", "postings_json")
