"""Drop report_comments.sentiment — the pos/neu/neg axis is gone.

Comments were labelled on two axes: a category and a sentiment towards the
product. The team reviewed the output and rejected the sentiment half: Thai
carries polarity through sarcasm, joke-complaints, particles and stretched
spelling, and the labels were not dependable enough to show a client. The
category set was rewritten as topics ("what is this comment about") and now
carries the whole analysis on its own.

The column is dropped rather than left unused, so the next person reading the
table does not find a populated column nothing writes to and assume it is live.
Its values were produced by rules the team has rejected, and every row is
re-labelled by the new rules on the next comment run anyway (comments.py stamps
CLASSIFY_VERSION, now "topic1", and re-does anything older).

Revision ID: 0018_drop_sentiment
Revises: 0017_rules_version
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_drop_sentiment"
down_revision = "0017_rules_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_report_comments_sentiment", table_name="report_comments")
    op.drop_column("report_comments", "sentiment")


def downgrade() -> None:
    # Recreates the column empty. The labels themselves are not recoverable, and
    # would be worthless if they were — they were made by superseded rules.
    op.add_column("report_comments",
                  sa.Column("sentiment", sa.String(length=8), nullable=True))
    op.create_index("ix_report_comments_sentiment", "report_comments", ["sentiment"])
