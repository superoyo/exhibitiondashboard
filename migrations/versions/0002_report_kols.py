"""report_kols table — editable roster for static campaign reports

Revision ID: 0002_report_kols
Revises: 0001_initial
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_report_kols"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_kols",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("display", sa.String(length=255), nullable=False),
        sa.Column("content_group", sa.String(length=64), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("username", name="uq_report_kols_username"),
    )
    op.create_index("ix_report_kols_username", "report_kols", ["username"])


def downgrade() -> None:
    op.drop_index("ix_report_kols_username", table_name="report_kols")
    op.drop_table("report_kols")
