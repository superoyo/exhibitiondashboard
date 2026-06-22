"""multi-campaign: report_kols/report_posts.campaign + report_kols.subgroup

Revision ID: 0005_campaigns
Revises: 0004_app_settings
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_campaigns"
down_revision = "0004_app_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("report_kols", sa.Column("subgroup", sa.String(length=64), nullable=True))
    op.add_column("report_kols", sa.Column("campaign", sa.String(length=32), nullable=False, server_default="pao"))
    op.create_index("ix_report_kols_campaign", "report_kols", ["campaign"])
    # username is now unique per-campaign, not globally
    op.drop_constraint("uq_report_kols_username", "report_kols", type_="unique")
    op.create_unique_constraint("uq_report_kols_campaign_username", "report_kols", ["campaign", "username"])

    op.add_column("report_posts", sa.Column("campaign", sa.String(length=32), nullable=False, server_default="pao"))
    op.create_index("ix_report_posts_campaign", "report_posts", ["campaign"])


def downgrade() -> None:
    op.drop_index("ix_report_posts_campaign", table_name="report_posts")
    op.drop_column("report_posts", "campaign")
    op.drop_constraint("uq_report_kols_campaign_username", "report_kols", type_="unique")
    op.create_unique_constraint("uq_report_kols_username", "report_kols", ["username"])
    op.drop_index("ix_report_kols_campaign", table_name="report_kols")
    op.drop_column("report_kols", "campaign")
    op.drop_column("report_kols", "subgroup")
