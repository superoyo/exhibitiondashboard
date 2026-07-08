"""campaigns.created_by / created_by_photo — who created each report
(captured from the Wazzup profile of the logged-in creator at create time).

Revision ID: 0014_created_by
Revises: 0013_sort_order
Create Date: 2027-07-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_created_by"
down_revision = "0013_sort_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("campaigns", sa.Column("created_by", sa.String(length=255), nullable=True))
    op.add_column("campaigns", sa.Column("created_by_photo", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("campaigns", "created_by_photo")
    op.drop_column("campaigns", "created_by")
