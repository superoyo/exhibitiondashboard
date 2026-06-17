"""Read-side query helpers used by the API routers. Pure SQLAlchemy, no HTTP."""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from sqlalchemy import Date, desc, func, select
from sqlalchemy.orm import Session

from app.models import Kol, KolDaily, Post, PostMetric, ScrapeRun

# metric key -> KolDaily column (for trend / sorting)
DAILY_METRICS = {
    "views": KolDaily.views_7d,
    "likes": KolDaily.likes_7d,
    "comments": KolDaily.comments_7d,
    "shares": KolDaily.shares_7d,
    "saves": KolDaily.saves_7d,
    "followers": KolDaily.followers,
    "posts": KolDaily.posts_7d,
}


def latest_scrape_date(session: Session) -> Optional[dt.date]:
    return session.scalar(select(func.max(KolDaily.scrape_date)))


def previous_scrape_date(session: Session, before: dt.date) -> Optional[dt.date]:
    return session.scalar(
        select(func.max(KolDaily.scrape_date)).where(KolDaily.scrape_date < before)
    )


def available_dates(session: Session) -> List[dt.date]:
    rows = session.execute(
        select(KolDaily.scrape_date).distinct().order_by(desc(KolDaily.scrape_date))
    ).all()
    return [r[0] for r in rows]


def resolve_date(session: Session, date_param: Optional[str]) -> Optional[dt.date]:
    """'latest' / None -> latest available; 'YYYY-MM-DD' -> that date."""
    if not date_param or date_param == "latest":
        return latest_scrape_date(session)
    return dt.date.fromisoformat(date_param)


def last_run(session: Session) -> Optional[ScrapeRun]:
    return session.scalars(
        select(ScrapeRun).order_by(desc(ScrapeRun.started_at)).limit(1)
    ).first()


def _kol_rows(session: Session, date: dt.date, group: Optional[str]) -> List[Dict[str, Any]]:
    q = (
        select(KolDaily, Kol)
        .join(Kol, Kol.id == KolDaily.kol_id)
        .where(KolDaily.scrape_date == date)
    )
    if group and group.lower() != "all":
        q = q.where(Kol.content_group == group)
    out = []
    for daily, kol in session.execute(q).all():
        out.append(
            {
                "username": kol.username,
                "display": kol.display,
                "group": kol.content_group,
                "followers": daily.followers,
                "posts_7d": daily.posts_7d,
                "views_7d": daily.views_7d,
                "likes_7d": daily.likes_7d,
                "comments_7d": daily.comments_7d,
                "shares_7d": daily.shares_7d,
                "saves_7d": daily.saves_7d,
                "engagement_rate": float(daily.engagement_rate) if daily.engagement_rate is not None else None,
            }
        )
    return out


def _pct_delta(curr: float, prev: float) -> Optional[float]:
    if prev == 0:
        return None
    return round((curr - prev) / prev * 100, 1)


def summary(session: Session, date: dt.date, group: Optional[str]) -> Dict[str, Any]:
    """KPI block (+ delta vs previous available date) and per-KOL list."""
    rows = _kol_rows(session, date, group)
    prev_date = previous_scrape_date(session, date)
    prev_rows = _kol_rows(session, prev_date, group) if prev_date else []
    prev_by_user = {r["username"]: r for r in prev_rows}

    def totals(rs: List[Dict[str, Any]]) -> Dict[str, float]:
        eng = sum(r["likes_7d"] + r["comments_7d"] + r["shares_7d"] for r in rs)
        views = sum(r["views_7d"] for r in rs)
        active = sum(1 for r in rs if r["posts_7d"] > 0)
        return {
            "total_views": views,
            "total_engagement": eng,
            "avg_engagement_rate": round(eng / views, 5) if views else 0,
            "total_posts": sum(r["posts_7d"] for r in rs),
            "active_kols": active,
            "total_followers": sum(r["followers"] for r in rs),
        }

    curr_t = totals(rows)
    prev_t = totals(prev_rows) if prev_rows else None

    kpis = {}
    for key, val in curr_t.items():
        prev_val = prev_t[key] if prev_t else None
        kpis[key] = {
            "value": val,
            "delta_pct": _pct_delta(val, prev_val) if prev_val is not None else None,
        }

    # attach per-KOL view delta vs previous day
    for r in rows:
        prev = prev_by_user.get(r["username"])
        r["delta_views_pct"] = _pct_delta(r["views_7d"], prev["views_7d"]) if prev else None

    return {
        "date": date.isoformat(),
        "previous_date": prev_date.isoformat() if prev_date else None,
        "available_dates": [d.isoformat() for d in available_dates(session)],
        "group": group or "all",
        "kpis": kpis,
        "kols": rows,
    }


def trend(session: Session, metric: str, group: Optional[str], days: int) -> Dict[str, Any]:
    """Time series of a metric summed across KOLs per scrape_date."""
    if metric == "engagement":
        col = KolDaily.likes_7d + KolDaily.comments_7d + KolDaily.shares_7d
    else:
        col = DAILY_METRICS.get(metric, KolDaily.views_7d)
    latest = latest_scrape_date(session)
    if latest is None:
        return {"metric": metric, "group": group or "all", "series": []}
    start = latest - dt.timedelta(days=days)

    agg = func.sum(col)
    q = (
        select(KolDaily.scrape_date, agg)
        .join(Kol, Kol.id == KolDaily.kol_id)
        .where(KolDaily.scrape_date >= start)
        .group_by(KolDaily.scrape_date)
        .order_by(KolDaily.scrape_date)
    )
    if group and group.lower() != "all":
        q = q.where(Kol.content_group == group)

    series = [{"date": d.isoformat(), "value": int(v or 0)} for d, v in session.execute(q).all()]
    return {"metric": metric, "group": group or "all", "days": days, "series": series}


def trend_by_group(session: Session, metric: str, days: int) -> Dict[str, Any]:
    """Same as trend() but split into one series per content group."""
    col = DAILY_METRICS.get(metric, KolDaily.views_7d)
    latest = latest_scrape_date(session)
    if latest is None:
        return {"metric": metric, "groups": {}}
    start = latest - dt.timedelta(days=days)
    q = (
        select(KolDaily.scrape_date, Kol.content_group, func.sum(col))
        .join(Kol, Kol.id == KolDaily.kol_id)
        .where(KolDaily.scrape_date >= start)
        .group_by(KolDaily.scrape_date, Kol.content_group)
        .order_by(KolDaily.scrape_date)
    )
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for d, g, v in session.execute(q).all():
        groups.setdefault(g, []).append({"date": d.isoformat(), "value": int(v or 0)})
    return {"metric": metric, "days": days, "groups": groups}


def posts_for(
    session: Session, date: dt.date, group: Optional[str], sort: str, limit: int
) -> List[Dict[str, Any]]:
    sort_col = {
        "views": PostMetric.views,
        "likes": PostMetric.likes,
        "comments": PostMetric.comments,
        "shares": PostMetric.shares,
        "saves": PostMetric.saves,
    }.get(sort, PostMetric.views)

    q = (
        select(Post, PostMetric, Kol)
        .join(PostMetric, PostMetric.post_id == Post.id)
        .join(Kol, Kol.id == Post.kol_id)
        .where(PostMetric.scrape_date == date)
        .order_by(desc(sort_col))
        .limit(limit)
    )
    if group and group.lower() != "all":
        q = q.where(Kol.content_group == group)

    out = []
    for post, m, kol in session.execute(q).all():
        out.append(
            {
                "username": kol.username,
                "display": kol.display,
                "group": kol.content_group,
                "video_id": post.video_id,
                "url": post.url,
                "posted_at": post.posted_at.isoformat() if post.posted_at else None,
                "is_pinned": post.is_pinned,
                "is_slideshow": post.is_slideshow,
                "views": m.views,
                "likes": m.likes,
                "comments": m.comments,
                "shares": m.shares,
                "saves": m.saves,
            }
        )
    return out


def kol_detail(session: Session, username: str, days: int = 30) -> Optional[Dict[str, Any]]:
    kol = session.scalars(select(Kol).where(Kol.username == username)).first()
    if not kol:
        return None

    latest = latest_scrape_date(session)
    trend_series = []
    if latest:
        start = latest - dt.timedelta(days=days)
        q = (
            select(KolDaily)
            .where(KolDaily.kol_id == kol.id, KolDaily.scrape_date >= start)
            .order_by(KolDaily.scrape_date)
        )
        for d in session.scalars(q).all():
            trend_series.append(
                {
                    "date": d.scrape_date.isoformat(),
                    "followers": d.followers,
                    "views_7d": d.views_7d,
                    "likes_7d": d.likes_7d,
                    "posts_7d": d.posts_7d,
                    "engagement_rate": float(d.engagement_rate) if d.engagement_rate is not None else None,
                }
            )

    posts = posts_for(session, latest, None, "views", 100) if latest else []
    posts = [p for p in posts if p["username"] == username]

    return {
        "username": kol.username,
        "display": kol.display,
        "group": kol.content_group,
        "trend": trend_series,
        "posts": posts,
    }
