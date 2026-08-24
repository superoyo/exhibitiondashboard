"""report_kols: per-KOL commercial fields — selling price, boost budget, KPI.

The planner team sells each KOL at a price, with a boost budget and a KPI that
varies per person (some are sold on Views, some on Impressions, some on
Interaction). None of this is derivable from any scrape — it exists only in the
planner's sheet — so the roster stores it, filled by the Excel import or edited
per row.

Exposure rule these columns were designed around: they ride ONLY on the
/api/roster/* endpoints, which require login. /api/report/data (open, read by
client links) must never serialize them — a client's report link is forwarded
to KOLs, and a KOL reading the price they are resold at is a business incident.

Revision ID: 0019_commercial
Revises: 0018_drop_sentiment
Create Date: 2026-08-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_commercial"
down_revision = "0018_drop_sentiment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Money as Numeric, not float: 12,500.50 must survive a round-trip exactly.
    op.add_column("report_kols",
                  sa.Column("cost_thb", sa.Numeric(12, 2), nullable=True))
    op.add_column("report_kols",
                  sa.Column("boost_thb", sa.Numeric(12, 2), nullable=True))
    # 'views' / 'impressions' / 'interaction' — free string, not an enum, so a
    # planner inventing a new unit next quarter is a data point, not a crash.
    op.add_column("report_kols",
                  sa.Column("kpi_metric", sa.String(length=16), nullable=True))
    op.add_column("report_kols",
                  sa.Column("kpi_target", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("report_kols", "kpi_target")
    op.drop_column("report_kols", "kpi_metric")
    op.drop_column("report_kols", "boost_thb")
    op.drop_column("report_kols", "cost_thb")
