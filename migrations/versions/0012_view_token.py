"""campaigns.view_token — random unguessable token for client view-only links
(/v/<token>), separate from the friendly /c/<key> so clients can't enumerate
other campaigns' reports.

Revision ID: 0012_view_token
Revises: 0011_post_caption
Create Date: 2027-07-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_view_token"
down_revision = "0011_post_caption"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("campaigns", sa.Column("view_token", sa.String(length=64), nullable=True))
    op.create_index("ix_campaigns_view_token", "campaigns", ["view_token"])


def downgrade() -> None:
    op.drop_index("ix_campaigns_view_token", table_name="campaigns")
    op.drop_column("campaigns", "view_token")
