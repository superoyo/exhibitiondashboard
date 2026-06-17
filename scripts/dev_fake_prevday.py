"""DEV-ONLY helper. Fabricate a previous-day snapshot from the latest real
scrape so you can eyeball KPI deltas and trend charts before you actually have
two days of history. NOT for production.

Run:  python scripts/dev_fake_prevday.py            # create N-1 day at 90% of latest
      python scripts/dev_fake_prevday.py --clean    # remove all fabricated days

It copies the latest kol_daily + post_metrics rows back `--days` day(s) and
scales the numbers by `--factor` so deltas are visible.
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.models import KolDaily, PostMetric  # noqa: E402


def fabricate(days: int, factor: float) -> None:
    with session_scope() as session:
        latest = session.scalar(select(func.max(KolDaily.scrape_date)))
        if latest is None:
            print("No data to copy. Run a scrape first.")
            return
        target = latest - dt.timedelta(days=days)

        # kol_daily
        n = 0
        for d in session.scalars(select(KolDaily).where(KolDaily.scrape_date == latest)).all():
            stmt = (
                pg_insert(KolDaily)
                .values(
                    kol_id=d.kol_id,
                    scrape_date=target,
                    followers=int(d.followers * factor),
                    posts_7d=d.posts_7d,
                    views_7d=int(d.views_7d * factor),
                    likes_7d=int(d.likes_7d * factor),
                    comments_7d=int(d.comments_7d * factor),
                    shares_7d=int(d.shares_7d * factor),
                    saves_7d=int(d.saves_7d * factor),
                    engagement_rate=d.engagement_rate,
                )
                .on_conflict_do_nothing(constraint="uq_kol_daily_day")
            )
            session.execute(stmt)
            n += 1

        # post_metrics (so /api/posts and detail still resolve on that date)
        for m in session.scalars(select(PostMetric).where(PostMetric.scrape_date == latest)).all():
            stmt = (
                pg_insert(PostMetric)
                .values(
                    post_id=m.post_id,
                    scrape_date=target,
                    views=int(m.views * factor),
                    likes=int(m.likes * factor),
                    comments=int(m.comments * factor),
                    shares=int(m.shares * factor),
                    saves=int(m.saves * factor),
                )
                .on_conflict_do_nothing(constraint="uq_post_metric_day")
            )
            session.execute(stmt)

        print(f"Fabricated snapshot for {target} ({n} KOLs) at factor {factor}. [DEV ONLY]")


def clean(real_date: dt.date | None) -> None:
    """Remove every day except the most recent real one."""
    with session_scope() as session:
        latest = session.scalar(select(func.max(KolDaily.scrape_date)))
        if latest is None:
            print("Nothing to clean.")
            return
        keep = real_date or latest
        session.execute(delete(KolDaily).where(KolDaily.scrape_date != keep))
        session.execute(delete(PostMetric).where(PostMetric.scrape_date != keep))
        print(f"Removed all snapshots except {keep}.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--factor", type=float, default=0.9)
    ap.add_argument("--clean", action="store_true")
    args = ap.parse_args()
    if args.clean:
        clean(None)
    else:
        fabricate(args.days, args.factor)
