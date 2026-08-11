"""report_comments.rules_version — which classification rules labelled a comment.

Improving the rules used to change nothing for comments already labelled,
because the classifier only ever looked at rows with no category at all. That
needed a separate "re-classify" button, which nobody could tell the purpose of.

With a version stamped on each row, the normal comment run re-labels anything
carrying an older version, and the extra button is gone. Same mechanism as
report_posts.tiein_hash, which already redoes shots produced by an older
algorithm.

Existing rows get NULL, which counts as "older than any version", so they are
re-labelled on the next run.

Revision ID: 0017_rules_version
Revises: 0016_comments
Create Date: 2026-08-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_rules_version"
down_revision = "0016_comments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("report_comments",
                  sa.Column("rules_version", sa.String(length=16), nullable=True))
    op.create_index("ix_report_comments_rules_version", "report_comments",
                    ["rules_version"])


def downgrade() -> None:
    op.drop_index("ix_report_comments_rules_version", table_name="report_comments")
    op.drop_column("report_comments", "rules_version")
