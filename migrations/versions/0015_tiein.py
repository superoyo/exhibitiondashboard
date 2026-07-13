"""report_posts.tiein_hash — image-cache key of the AI-picked product tie-in
frame extracted from the post's video (used by the PPTX post preview).

Revision ID: 0015_tiein
Revises: 0014_created_by
Create Date: 2027-07-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_tiein"
down_revision = "0014_created_by"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("report_posts", sa.Column("tiein_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("report_posts", "tiein_hash")
