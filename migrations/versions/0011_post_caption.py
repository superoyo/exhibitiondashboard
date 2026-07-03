"""report_posts.caption — post text, used to compose the post-screenshot card
in the generated PowerPoint report

Revision ID: 0011_post_caption
Revises: 0010_multiplatform
Create Date: 2027-07-03
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_post_caption"
down_revision = "0010_multiplatform"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("report_posts", sa.Column("caption", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("report_posts", "caption")
