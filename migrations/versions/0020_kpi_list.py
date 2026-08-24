"""KPIs become lists, and groups get their own.

Two facts from the planner's actual sheets that the one-metric-per-KOL model
(0019) could not hold:

  - one KOL can be sold on TWO KPIs at once (Views AND Engagement)
  - a package group is sold on a TOTAL for the whole group ("7M Impressions
    across Micro Package"), which belongs to no single row

So report_kols.kpi_metric/kpi_target become report_kols.kpi_json — a JSON list
of {"metric","target"} — with existing single values carried over, and a new
report_group_kpis table stores per-(campaign, group) KPI lists, keyed by the
group NAME because that is what roster rows carry; renaming a group in the
roster orphans its KPI row, which the editing UI surfaces rather than hides.

Same exposure rule as 0019: all of it rides only on authenticated /api/roster/*
endpoints.

Revision ID: 0020_kpi_list
Revises: 0019_commercial
Create Date: 2026-08-24
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "0020_kpi_list"
down_revision = "0019_commercial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("report_kols", sa.Column("kpi_json", sa.Text(), nullable=True))

    # Carry over the single (metric, target) pairs 0019 stored.
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, kpi_metric, kpi_target FROM report_kols "
        "WHERE kpi_target IS NOT NULL")).all()
    for rid, metric, target in rows:
        payload = json.dumps([{"metric": metric or "", "target": int(target)}])
        conn.execute(sa.text("UPDATE report_kols SET kpi_json = :j WHERE id = :i"),
                     {"j": payload, "i": rid})

    op.drop_column("report_kols", "kpi_target")
    op.drop_column("report_kols", "kpi_metric")

    op.create_table(
        "report_group_kpis",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campaign", sa.String(length=32), nullable=False),
        sa.Column("group_name", sa.String(length=64), nullable=False),
        sa.Column("kpi_json", sa.Text(), nullable=False),
        sa.UniqueConstraint("campaign", "group_name",
                            name="uq_report_group_kpis_campaign_group"),
    )
    op.create_index("ix_report_group_kpis_campaign", "report_group_kpis", ["campaign"])


def downgrade() -> None:
    op.drop_index("ix_report_group_kpis_campaign", table_name="report_group_kpis")
    op.drop_table("report_group_kpis")

    op.add_column("report_kols",
                  sa.Column("kpi_metric", sa.String(length=16), nullable=True))
    op.add_column("report_kols",
                  sa.Column("kpi_target", sa.BigInteger(), nullable=True))
    # A list cannot fit back into one slot — keep the FIRST KPI, drop the rest.
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, kpi_json FROM report_kols WHERE kpi_json IS NOT NULL")).all()
    for rid, payload in rows:
        try:
            first = (json.loads(payload) or [{}])[0]
        except Exception:  # noqa: BLE001
            continue
        if first.get("target"):
            conn.execute(sa.text(
                "UPDATE report_kols SET kpi_metric = :m, kpi_target = :t "
                "WHERE id = :i"),
                {"m": (first.get("metric") or "")[:16] or None,
                 "t": int(first["target"]), "i": rid})
    op.drop_column("report_kols", "kpi_json")
