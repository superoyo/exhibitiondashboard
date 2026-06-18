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
from app.apify_client import ApifyError, run_scrape_posts
from app.aggregate import _parse_posted_at, _to_int
from app.db import session_scope
from app.models import ReportKol, ReportPost

log = logging.getLogger("report_refresh")


def video_id_of(url: Optional[str]) -> str:
    """Extract the TikTok video id from a post URL ('.../video/<id>?...')."""
    if not url or "/video/" not in url:
        return ""
    return url.rstrip("/").split("/video/")[-1].split("?")[0].strip()

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
            roster = [(k.username.strip().lower(), k.url) for k in kols]
        usernames = {u for u, _ in roster}
        urls = [url for _, url in roster if url]
        REFRESH_STATE["kol_count"] = len(roster)

        if not urls:
            REFRESH_STATE.update(
                status="failed",
                message="ไม่มีลิงก์โพสต์ใน KOL ที่ติ๊ก active — ใส่ลิงก์โพสต์ในหน้าแก้ไข KOL ก่อน",
                finished_at=dt.datetime.now(config.TZ).isoformat())
            return {"status": "skipped", "reason": "no post URLs"}

        log.info("Report refresh: scraping %d post URLs", len(urls))
        items, meta = run_scrape_posts(urls)
        posts, profile = _parse_report_items(items)

        # Match scraped posts to the roster by USERNAME (robust to short links
        # like vt.tiktok.com that carry no /video/ id). One post per KOL.
        by_user: Dict[str, Dict] = {}
        for p in posts:
            u = p["username"]
            if u in usernames and (u not in by_user or p["views"] > by_user[u]["views"]):
                by_user[u] = p

        with session_scope() as session:
            session.execute(delete(ReportPost).where(ReportPost.username.in_(usernames)))
            for p in by_user.values():
                session.add(ReportPost(**p))
            for k in session.scalars(select(ReportKol).where(ReportKol.username.in_(usernames))).all():
                pr = profile.get(k.username.lower())
                if pr:
                    if pr["followers"]:
                        k.followers = pr["followers"]
                    if pr["nick"] and (not k.display or k.display == k.username):
                        k.display = pr["nick"]

        seen = set(by_user)
        missing = len(usernames) - len(seen)
        msg = f"อัปเดตแล้ว {len(seen)}/{len(usernames)} โพสต์"
        if missing > 0:
            msg += f" (ดึงไม่ได้ {missing} — ลิงก์อาจผิด/โพสต์ถูกลบ)"
        REFRESH_STATE.update(
            status="success", message=msg,
            finished_at=dt.datetime.now(config.TZ).isoformat(),
            posts=len(seen), cost_usd=meta.get("cost_usd"),
        )
        log.info("Report refresh done: %d/%d posts, cost=%s", len(seen), len(urls), meta.get("cost_usd"))
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
