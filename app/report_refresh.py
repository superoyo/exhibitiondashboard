"""Refresh the report dataset on demand (the 'Refresh Data' button).

Scrapes the trailing 7-day window via Apify for ONLY the active (ticked)
report_kols, then replaces their rows in report_posts and updates follower
counts. Runs in a background task; progress is exposed via REFRESH_STATE.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import delete, select

from app import config
from app.apify_client import ApifyError, oldest_date_for, run_scrape
from app.aggregate import _parse_posted_at, _to_int
from app.db import session_scope
from app.models import ReportKol, ReportPost

log = logging.getLogger("report_refresh")

# Single-worker in-memory progress for the UI to poll.
REFRESH_STATE: Dict[str, Any] = {
    "status": "idle",          # idle | running | success | failed
    "message": "",
    "started_at": None,
    "finished_at": None,
    "kol_count": 0,
    "posts": 0,
    "cost_usd": None,
}


def _today() -> dt.date:
    return dt.datetime.now(config.TZ).date()


def _parse_report_items(items: List[Dict[str, Any]]):
    """Return (posts, profile) where profile maps username -> {followers, nick}."""
    posts: List[Dict[str, Any]] = []
    profile: Dict[str, Dict[str, Any]] = {}
    for it in items:
        author = it.get("authorMeta") or {}
        username = (it.get("input") or author.get("name") or "").strip().lower()
        if username:
            p = profile.setdefault(username, {"followers": 0, "nick": ""})
            if author.get("fans") is not None:
                p["followers"] = _to_int(author.get("fans"))
            if author.get("nickName"):
                p["nick"] = author.get("nickName")

        video_id = it.get("id")
        if not video_id:
            continue
        posts.append({
            "username": username,
            "video_id": str(video_id),
            "url": it.get("webVideoUrl"),
            "cover_url": (it.get("videoMeta") or {}).get("coverUrl"),
            "posted_at": _parse_posted_at(it.get("createTimeISO")),
            "views": _to_int(it.get("playCount")),
            "likes": _to_int(it.get("diggCount")),
            "comments": _to_int(it.get("commentCount")),
            "shares": _to_int(it.get("shareCount")),
            "saves": _to_int(it.get("collectCount")),
        })
    return posts, profile


def refresh_report() -> dict:
    """Scrape active report KOLs (7-day window) and replace their posts.

    Never raises — records the outcome in REFRESH_STATE.
    """
    REFRESH_STATE.update(
        status="running", message="กำลังดึงข้อมูลจาก Apify…",
        started_at=dt.datetime.now(config.TZ).isoformat(), finished_at=None,
        posts=0, cost_usd=None,
    )
    try:
        with session_scope() as session:
            kols = session.scalars(
                select(ReportKol).where(ReportKol.active.is_(True))
            ).all()
            usernames = [k.username.strip().lower() for k in kols]
        REFRESH_STATE["kol_count"] = len(usernames)

        if not usernames:
            REFRESH_STATE.update(status="failed", message="ไม่มี KOL ที่ติ๊ก active ในรายงาน",
                                 finished_at=dt.datetime.now(config.TZ).isoformat())
            return {"status": "skipped", "reason": "no active report KOLs"}

        oldest = oldest_date_for(_today(), config.LOOKBACK_DAYS)
        log.info("Report refresh: %d KOLs, oldest=%s", len(usernames), oldest)

        items, meta = run_scrape(usernames, oldest)
        posts, profile = _parse_report_items(items)

        with session_scope() as session:
            # Replace posts for the refreshed usernames (current 7-day snapshot).
            session.execute(delete(ReportPost).where(ReportPost.username.in_(usernames)))
            seen = set()
            for p in posts:
                if p["username"] not in usernames or p["video_id"] in seen:
                    continue
                seen.add(p["video_id"])
                session.add(ReportPost(**p))
            # Update followers + fill display from nickName when still blank.
            for k in session.scalars(select(ReportKol).where(ReportKol.username.in_(usernames))).all():
                pr = profile.get(k.username.lower())
                if pr:
                    if pr["followers"]:
                        k.followers = pr["followers"]
                    if pr["nick"] and (not k.display or k.display == k.username):
                        k.display = pr["nick"]

        REFRESH_STATE.update(
            status="success",
            message=f"อัปเดตแล้ว {len(seen)} โพสต์ จาก {len(usernames)} KOL",
            finished_at=dt.datetime.now(config.TZ).isoformat(),
            posts=len(seen), cost_usd=meta.get("cost_usd"),
        )
        log.info("Report refresh done: %d posts, cost=%s", len(seen), meta.get("cost_usd"))
        return {"status": "success", "posts": len(seen), "cost_usd": meta.get("cost_usd")}

    except (ApifyError, httpx.HTTPError) as exc:
        log.error("Report refresh failed: %s", exc)
        REFRESH_STATE.update(status="failed", message=f"ดึงข้อมูลล้มเหลว: {exc}",
                             finished_at=dt.datetime.now(config.TZ).isoformat())
        return {"status": "failed", "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        log.exception("Report refresh crashed")
        REFRESH_STATE.update(status="failed", message=f"ผิดพลาด: {exc}",
                             finished_at=dt.datetime.now(config.TZ).isoformat())
        return {"status": "failed", "error": str(exc)}
