"""campaigns metadata table — makes campaigns dynamic (created from the UI)

Revision ID: 0008_campaigns_meta
Revises: 0007_roster_avatar
Create Date: 2027-01-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_campaigns_meta"
down_revision = "0007_roster_avatar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("key", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("emoji", sa.String(length=8), nullable=False, server_default="📊"),
        sa.Column("subtitle", sa.Text(), nullable=True),
        sa.Column("groups_json", sa.Text(), nullable=True),
        sa.Column("subgroups_json", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_campaigns_created_at", "campaigns", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_campaigns_created_at", table_name="campaigns")
    op.drop_table("campaigns")
