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
from app.apify_client import ApifyError, run_scrape_fb, run_scrape_posts
from app.aggregate import _parse_posted_at, _to_int
from app.db import session_scope
from app.models import ReportKol, ReportPost

log = logging.getLogger("report_refresh")


def video_id_of(url: Optional[str]) -> str:
    """Extract the TikTok video id from a post URL ('.../video/<id>?...')."""
    if not url or "/video/" not in url:
        return ""
    return url.rstrip("/").split("/video/")[-1].split("?")[0].strip()


def is_fb(url: Optional[str]) -> bool:
    u = (url or "").lower()
    return "facebook.com" in u or "fb.watch" in u


def _parse_fb_items(items):
    """Parse Facebook actor items → (posts, profile). FB has no views/saves;
    engagement = likes + comments + shares. Matched to the roster by pageName."""
    posts, profile = [], {}
    for it in items:
        page = (it.get("pageName") or "").strip().lower()
        if not page:
            continue
        user = it.get("user") or {}
        profile[page] = {"followers": 0, "nick": user.get("name") or it.get("pageName")}
        pid = str(it.get("postId") or "")
        posts.append({
            "username": page,
            "video_id": ("fb_" + pid)[:64] if pid else ("fb_" + page)[:64],
            "url": it.get("facebookUrl") or it.get("url"),
            "cover_url": user.get("profilePic"),
            "posted_at": _parse_posted_at(it.get("time")),
            "views": _to_int(it.get("viewsCount") or it.get("videoViewCount") or 0),
            "likes": _to_int(it.get("likes")),
            "comments": _to_int(it.get("comments")),
            "shares": _to_int(it.get("shares")),
            "saves": 0,
        })
    return posts, profile

# Single-worker in-memory progress for the UI to poll.
def _new_state() -> Dict[str, Any]:
    return {"status": "idle", "message": "", "started_at": None,
            "finished_at": None, "kol_count": 0, "posts": 0, "cost_usd": None}


# Per-campaign in-memory progress (single worker). 'pao' kept as the default
# key so the legacy no-arg endpoints keep working.
REFRESH_STATES: Dict[str, Dict[str, Any]] = {"pao": _new_state(), "sahagroup": _new_state()}


def state_for(campaign: str) -> Dict[str, Any]:
    return REFRESH_STATES.setdefault(campaign, _new_state())


# Backwards-compatible alias (PAO).
REFRESH_STATE = REFRESH_STATES["pao"]


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


def refresh_report(campaign: str = "pao") -> dict:
    """Scrape the active roster of one campaign by post URL and replace its
    posts. Never raises — records the outcome in state_for(campaign)."""
    st = state_for(campaign)
    st.update(status="running", message="กำลังดึงข้อมูลจาก Apify…",
              started_at=dt.datetime.now(config.TZ).isoformat(), finished_at=None,
              posts=0, cost_usd=None)
    try:
        with session_scope() as session:
            kols = session.scalars(
                select(ReportKol).where(
                    ReportKol.active.is_(True), ReportKol.campaign == campaign)
            ).all()
            roster = [(k.username.strip().lower(), k.url) for k in kols]
        usernames = {u for u, _ in roster}
        urls = [url for _, url in roster if url]
        st["kol_count"] = len(roster)

        if not urls:
            st.update(status="failed",
                      message="ยังไม่มีลิงก์โพสต์ใน KOL ที่ติ๊ก active — ใส่ลิงก์ในหน้าแก้ไข KOL ก่อน",
                      finished_at=dt.datetime.now(config.TZ).isoformat())
            return {"status": "skipped", "reason": "no post URLs"}

        tt_urls = [u for u in urls if not is_fb(u)]
        fb_urls = [u for u in urls if is_fb(u)]
        log.info("Refresh[%s]: %d TikTok + %d Facebook URLs", campaign, len(tt_urls), len(fb_urls))

        posts, profile, cost = [], {}, 0.0
        if tt_urls:
            items, meta = run_scrape_posts(tt_urls)
            p, pr = _parse_report_items(items)
            posts += p; profile.update(pr)
            if meta.get("cost_usd"):
                cost += meta["cost_usd"]
        if fb_urls:
            items, meta = run_scrape_fb(fb_urls)
            p, pr = _parse_fb_items(items)
            posts += p; profile.update(pr)
            if meta.get("cost_usd"):
                cost += meta["cost_usd"]

        by_user: Dict[str, Dict] = {}
        for p in posts:
            u = p["username"]
            if u in usernames and (u not in by_user or p["views"] > by_user[u]["views"]):
                by_user[u] = p

        with session_scope() as session:
            session.execute(delete(ReportPost).where(
                ReportPost.campaign == campaign, ReportPost.username.in_(usernames)))
            for p in by_user.values():
                session.add(ReportPost(campaign=campaign, **p))
            for k in session.scalars(select(ReportKol).where(
                    ReportKol.campaign == campaign, ReportKol.username.in_(usernames))).all():
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
        try:
            from app.settings import add_cost
            add_cost(campaign, cost)
        except Exception as exc:  # noqa: BLE001 — cost tracking must not break refresh
            log.warning("add_cost failed: %s", exc)
        st.update(status="success", message=msg,
                  finished_at=dt.datetime.now(config.TZ).isoformat(),
                  posts=len(seen), cost_usd=round(cost, 4) if cost else None)
        log.info("Refresh[%s] done: %d/%d posts, cost=%s", campaign, len(seen), len(usernames), cost)
        return {"status": "success", "posts": len(seen), "cost_usd": round(cost, 4) if cost else None}

    except (ApifyError, httpx.HTTPError) as exc:
        log.error("Refresh[%s] failed: %s", campaign, exc)
        st.update(status="failed", message=f"ดึงข้อมูลล้มเหลว: {exc}",
                  finished_at=dt.datetime.now(config.TZ).isoformat())
        return {"status": "failed", "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        log.exception("Refresh[%s] crashed", campaign)
        st.update(status="failed", message=f"ผิดพลาด: {exc}",
                  finished_at=dt.datetime.now(config.TZ).isoformat())
        return {"status": "failed", "error": str(exc)}
