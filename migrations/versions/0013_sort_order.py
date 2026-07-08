"""report_kols.sort_order — preserve the row order of the imported file so the
roster and report list KOLs in the same order as the team's Excel/Sheet.

Revision ID: 0013_sort_order
Revises: 0012_view_token
Create Date: 2027-07-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_sort_order"
down_revision = "0012_view_token"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("report_kols", sa.Column("sort_order", sa.Integer(),
                                           nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("report_kols", "sort_order")
