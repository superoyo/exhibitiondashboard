"""report_kols.cost_note / boost_note — "Quota" and "Package" money cells.

The planner's sheets sometimes put a WORD where a money figure would be:
"Quota" (the client spends a posting quota bought earlier — no new charge)
or "Package" (sold as a bundle, no per-head price). Those cells imported as
blank, and the team reads blank as "missing data". The word is now stored
per KOL and rendered verbatim in the ค่าตัว/บูส columns (team, 2026-09-18,
Pao Win Wash being the case in point).

Same exposure rule as the amounts themselves: authenticated roster routes
plus the token-addressed /api/view/<token>/commercial — never the open,
campaign-key-addressed report data.

Revision ID: 0022_money_notes
Revises: 0021_channel_baselines
Create Date: 2026-09-18
"""
import sqlalchemy as sa
from alembic import op

revision = "0022_money_notes"
down_revision = "0021_channel_baselines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("report_kols", sa.Column("cost_note", sa.String(length=32), nullable=True))
    op.add_column("report_kols", sa.Column("boost_note", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("report_kols", "boost_note")
    op.drop_column("report_kols", "cost_note")
