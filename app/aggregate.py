"""Parse Apify items and persist them idempotently, then roll up per-KOL daily
summaries. See brief sections 6.3, 8, 9.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app import config
from app.models import Kol, KolDaily, Post, PostMetric

log = logging.getLogger("aggregate")


def _to_int(v: Any) -> int:
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0


def _parse_posted_at(v: Any) -> Optional[dt.datetime]:
    if not v:
        return None
    try:
        # Apify returns e.g. "2026-06-10T08:30:00.000Z"
        return dt.datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_items(items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Split raw Apify items into (valid post dicts, followers-by-username).

    Items without an `id` (profiles with no recent posts / errors) are dropped
    from posts, but their follower count is still captured if present.
    """
    posts: List[Dict[str, Any]] = []
    followers: Dict[str, int] = {}

    for it in items:
        username = (it.get("input") or it.get("authorMeta", {}).get("name") or "").strip()
        author = it.get("authorMeta") or {}
        fans = author.get("fans")
        if username and fans is not None:
            followers[username.lower()] = _to_int(fans)

        video_id = it.get("id")
        if not video_id:
            continue  # profile-only / error result — keep follower, skip post

        posts.append(
            {
                "username": username.lower(),
                "video_id": str(video_id),
                "url": it.get("webVideoUrl"),
                "posted_at": _parse_posted_at(it.get("createTimeISO")),
                "is_pinned": bool(it.get("isPinned", False)),
                "is_slideshow": bool(it.get("isSlideshow", False)),
                "views": _to_int(it.get("playCount")),
                "likes": _to_int(it.get("diggCount")),
                "comments": _to_int(it.get("commentCount")),
                "shares": _to_int(it.get("shareCount")),
                "saves": _to_int(it.get("collectCount")),
            }
        )

    return posts, followers


def _kol_map(session: Session) -> Dict[str, Kol]:
    return {k.username.lower(): k for k in session.scalars(select(Kol)).all()}


def persist_posts(session: Session, run_date: dt.date, parsed: List[Dict[str, Any]]) -> int:
    """Upsert posts + post_metrics. Returns number of post metrics written."""
    kols = _kol_map(session)
    written = 0

    for p in parsed:
        kol = kols.get(p["username"])
        if not kol:
            log.warning("Post for unknown KOL username=%s (skipped)", p["username"])
            continue

        # Upsert post (by unique video_id). first_seen set on insert only.
        post_stmt = (
            pg_insert(Post)
            .values(
                kol_id=kol.id,
                video_id=p["video_id"],
                url=p["url"],
                posted_at=p["posted_at"],
                is_pinned=p["is_pinned"],
                is_slideshow=p["is_slideshow"],
                first_seen=run_date,
                last_scraped=run_date,
            )
            .on_conflict_do_update(
                index_elements=[Post.video_id],
                set_={
                    "url": p["url"],
                    "posted_at": p["posted_at"],
                    "is_pinned": p["is_pinned"],
                    "is_slideshow": p["is_slideshow"],
                    "last_scraped": run_date,
                },
            )
            .returning(Post.id)
        )
        post_id = session.execute(post_stmt).scalar_one()

        # Upsert metric snapshot for this scrape_date.
        metric_stmt = (
            pg_insert(PostMetric)
            .values(
                post_id=post_id,
                scrape_date=run_date,
                views=p["views"],
                likes=p["likes"],
                comments=p["comments"],
                shares=p["shares"],
                saves=p["saves"],
            )
            .on_conflict_do_update(
                constraint="uq_post_metric_day",
                set_={
                    "views": p["views"],
                    "likes": p["likes"],
                    "comments": p["comments"],
                    "shares": p["shares"],
                    "saves": p["saves"],
                },
            )
        )
        session.execute(metric_stmt)
        written += 1

    session.flush()
    return written


def compute_kol_daily(
    session: Session, run_date: dt.date, followers: Dict[str, int]
) -> int:
    """Roll up the trailing 7-day window per KOL into kol_daily (upsert).

    Every active KOL gets a row — those with no posts in window get zeros
    (followers preserved when known). Returns number of rows written.
    """
    window_start = run_date - dt.timedelta(days=config.LOOKBACK_DAYS)
    kols = session.scalars(select(Kol).where(Kol.active.is_(True))).all()
    rows = 0

    for kol in kols:
        # Posts by this KOL posted within the trailing window, using the metric
        # snapshot captured on this run_date.
        q = (
            select(
                PostMetric.views,
                PostMetric.likes,
                PostMetric.comments,
                PostMetric.shares,
                PostMetric.saves,
            )
            .join(Post, Post.id == PostMetric.post_id)
            .where(
                Post.kol_id == kol.id,
                PostMetric.scrape_date == run_date,
                Post.posted_at.is_not(None),
                Post.posted_at >= dt.datetime.combine(window_start, dt.time.min),
            )
        )
        metrics = session.execute(q).all()

        posts_7d = len(metrics)
        views = sum(m.views for m in metrics)
        likes = sum(m.likes for m in metrics)
        comments = sum(m.comments for m in metrics)
        shares = sum(m.shares for m in metrics)
        saves = sum(m.saves for m in metrics)
        er = round((likes + comments + shares) / views, 5) if views > 0 else None
        fans = followers.get(kol.username.lower(), 0)

        stmt = (
            pg_insert(KolDaily)
            .values(
                kol_id=kol.id,
                scrape_date=run_date,
                followers=fans,
                posts_7d=posts_7d,
                views_7d=views,
                likes_7d=likes,
                comments_7d=comments,
                shares_7d=shares,
                saves_7d=saves,
                engagement_rate=er,
            )
            .on_conflict_do_update(
                constraint="uq_kol_daily_day",
                set_={
                    # keep last known followers if this run didn't return it
                    "followers": fans if fans else KolDaily.followers,
                    "posts_7d": posts_7d,
                    "views_7d": views,
                    "likes_7d": likes,
                    "comments_7d": comments,
                    "shares_7d": shares,
                    "saves_7d": saves,
                    "engagement_rate": er,
                },
            )
        )
        session.execute(stmt)
        rows += 1

    session.flush()
    return rows
