"""Refresh the report dataset on demand (the 'Refresh Data' button).

Scrapes the trailing 7-day window via Apify for ONLY the active (ticked)
report_kols, then replaces their rows in report_posts and updates follower
counts. Runs in a background task; progress is exposed via REFRESH_STATE.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Any, Dict, List, Optional

import json

import httpx
from sqlalchemy import delete, select

from app import config
from app.apify_client import (
    ApifyError,
    run_scrape_fb,
    run_scrape_ig,
    run_scrape_posts,
    run_scrape_profiles,
    run_scrape_x,
    run_scrape_yt,
)
from app.aggregate import _parse_posted_at, _to_int
from app.db import session_scope
from app.models import ReportKol, ReportPost

log = logging.getLogger("report_refresh")

# Apify puts the token in the request URL, so httpx error strings leak it.
# Redact before any error text reaches the UI/status.
_TOKEN_RE = re.compile(r"(token=)[^&\s'\"]+", re.I)


def _redact(exc) -> str:
    return _TOKEN_RE.sub(r"\1***", str(exc))


def video_id_of(url: Optional[str]) -> str:
    """Extract the TikTok video id from a post URL ('.../video/<id>?...')."""
    if not url or "/video/" not in url:
        return ""
    return url.rstrip("/").split("/video/")[-1].split("?")[0].strip()


def is_fb(url: Optional[str]) -> bool:
    u = (url or "").lower()
    return "facebook.com" in u or "fb.watch" in u


def platform_of(url: Optional[str]) -> str:
    """Classify a post URL into a platform key."""
    u = (url or "").lower()
    if "tiktok.com" in u:
        return "tiktok"
    if "facebook.com" in u or "fb.watch" in u or "fb.com" in u:
        return "facebook"
    if "instagram.com" in u:
        return "instagram"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if "x.com" in u or "twitter.com" in u:
        return "x"
    if "line.me" in u:
        return "line"
    return "other"


def handle_from_url(url: Optional[str]) -> str:
    """Best-effort account handle from a post URL (for matching scraped posts)."""
    import re as _re
    u = url or ""
    for pat in (r"tiktok\.com/@([^/?#\s]+)", r"(?:facebook\.com|fb\.com)/([^/?#\s]+)",
                r"instagram\.com/([^/?#\s]+)", r"(?:x\.com|twitter\.com)/([^/?#\s]+)",
                r"youtube\.com/@([^/?#\s]+)"):
        m = _re.search(pat, u, _re.I)
        if m:
            return m.group(1).lower()
    return ""


def kol_links(k) -> list:
    """All (platform,url,handle) links for a KOL — from links_json, else the
    single url column (pre-multiplatform data)."""
    raw = getattr(k, "links_json", None)
    if raw:
        try:
            out = []
            for ln in json.loads(raw):
                url = (ln.get("url") or "").strip()
                if not url:
                    continue
                out.append({
                    "platform": ln.get("platform") or platform_of(url),
                    "url": url,
                    "handle": (ln.get("handle") or handle_from_url(url) or k.username).lower(),
                })
            if out:
                return out
        except Exception:  # noqa: BLE001 — malformed json falls back to url
            pass
    if k.url:
        return [{"platform": platform_of(k.url), "url": k.url,
                 "handle": (handle_from_url(k.url) or k.username).lower()}]
    return []


def _parse_ig_items(items):
    posts = []
    for it in items:
        handle = (it.get("ownerUsername") or "").strip().lower()
        vid = str(it.get("id") or it.get("shortCode") or "")
        if not vid:
            continue
        sc = it.get("shortCode")
        posts.append({
            "username": handle, "video_id": vid,
            "url": it.get("url") or (f"https://www.instagram.com/p/{sc}/" if sc else None),
            "cover_url": it.get("displayUrl") or it.get("thumbnailUrl"), "avatar_url": None,
            "posted_at": _parse_posted_at(it.get("timestamp")),
            "views": _to_int(it.get("videoViewCount") or it.get("videoPlayCount") or 0),
            "likes": _to_int(it.get("likesCount")), "comments": _to_int(it.get("commentsCount")),
            "shares": 0, "saves": 0,
        })
    return posts


def _parse_yt_items(items):
    posts = []
    for it in items:
        handle = (it.get("channelName") or it.get("channelUsername") or "").strip().lstrip("@").lower()
        vid = str(it.get("id") or it.get("videoId") or "")
        if not vid:
            continue
        posts.append({
            "username": handle, "video_id": vid, "url": it.get("url"),
            "cover_url": it.get("thumbnailUrl"), "avatar_url": None,
            "posted_at": _parse_posted_at(it.get("date") or it.get("uploadDate")),
            "views": _to_int(it.get("viewCount")), "likes": _to_int(it.get("likes")),
            "comments": _to_int(it.get("commentsCount")), "shares": 0, "saves": 0,
        })
    return posts


def _parse_x_items(items):
    posts = []
    for it in items:
        au = it.get("author") or {}
        handle = (au.get("userName") or it.get("username") or "").strip().lstrip("@").lower()
        vid = str(it.get("id") or it.get("id_str") or "")
        if not vid:
            continue
        posts.append({
            "username": handle, "video_id": vid,
            "url": it.get("url") or it.get("twitterUrl"),
            "cover_url": None, "avatar_url": au.get("profilePicture"),
            "posted_at": _parse_posted_at(it.get("createdAt")),
            "views": _to_int(it.get("viewCount")), "likes": _to_int(it.get("likeCount")),
            "comments": _to_int(it.get("replyCount")), "shares": _to_int(it.get("retweetCount")),
            "saves": _to_int(it.get("bookmarkCount")),
        })
    return posts


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
            "avatar_url": user.get("profilePic"),
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
REFRESH_STATES: Dict[str, Dict[str, Any]] = {
    "pao": _new_state(),
    "sahagroup": _new_state(),
    "sahagroup2027": _new_state(),
}


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
            "avatar_url": author.get("avatar") or author.get("originalAvatarUrl"),
            "posted_at": _parse_posted_at(it.get("createTimeISO")),
            "views": _to_int(it.get("playCount")),
            "likes": _to_int(it.get("diggCount")),
            "comments": _to_int(it.get("commentCount")),
            "shares": _to_int(it.get("shareCount")),
            "saves": _to_int(it.get("collectCount")),
        })
    return posts, profile


def _scrape_and_apply_profiles(campaign: str, handles) -> dict:
    """Scrape TikTok profiles for `handles` and write avatar/followers/display
    onto the campaign's active ReportKol rows. Returns {done, cost}.
    Shared by the standalone profile fetch and the merged Refresh Data flow."""
    handles = list(handles)
    if not handles:
        return {"done": 0, "cost": 0.0}
    items, meta = run_scrape_profiles(handles)
    prof: Dict[str, Dict] = {}
    for it in items:
        a = it.get("authorMeta") or {}
        name = (it.get("input") or a.get("name") or "").strip().lower()
        if not name:
            continue
        d = prof.setdefault(name, {})
        av = a.get("avatar") or a.get("originalAvatarUrl")
        if av:
            d["avatar"] = av
        if a.get("fans") is not None:
            d["fans"] = _to_int(a.get("fans"))
        if a.get("nickName"):
            d["nick"] = a.get("nickName")

    done = 0
    with session_scope() as session:
        for k in session.scalars(select(ReportKol).where(
                ReportKol.active.is_(True), ReportKol.campaign == campaign)).all():
            p = prof.get(k.username.lower())
            if not p:
                continue
            if p.get("avatar"):
                k.avatar_url = p["avatar"]; done += 1
            if p.get("fans"):
                k.followers = p["fans"]
            if p.get("nick") and (not k.display or k.display == k.username):
                k.display = p["nick"]
    return {"done": done, "cost": meta.get("cost_usd") or 0.0}


def fetch_profiles(campaign: str = "sahagroup") -> dict:
    """Scrape TikTok PROFILES of the active roster (no post links needed) to
    fill avatar + followers + display. Progress in state_for('pf:'+campaign)."""
    st = state_for("pf:" + campaign)
    st.update(status="running", message="กำลังดึงรูปโปรไฟล์จาก Apify…",
              started_at=dt.datetime.now(config.TZ).isoformat(), finished_at=None,
              posts=0, cost_usd=None)
    try:
        with session_scope() as session:
            kols = session.scalars(select(ReportKol).where(
                ReportKol.active.is_(True), ReportKol.campaign == campaign)).all()
            # profiles = TikTok handles only (skip Facebook pages)
            usernames = [k.username.strip().lower() for k in kols
                         if k.content_group != "Facebook" and not is_fb(k.url)]
        st["kol_count"] = len(usernames)
        if not usernames:
            st.update(status="failed", message="ไม่มี KOL TikTok ที่ active",
                      finished_at=dt.datetime.now(config.TZ).isoformat())
            return {"status": "skipped"}

        log.info("Profiles[%s]: scraping %d profiles", campaign, len(usernames))
        res = _scrape_and_apply_profiles(campaign, usernames)
        done = res["done"]
        cost = res["cost"]
        try:
            from app.settings import add_cost
            add_cost(campaign, cost)
        except Exception:  # noqa: BLE001
            pass
        st.update(status="success", message=f"ดึงรูปโปรไฟล์แล้ว {done}/{len(usernames)} ราย",
                  finished_at=dt.datetime.now(config.TZ).isoformat(),
                  posts=done, cost_usd=round(cost, 4) if cost else None)
        log.info("Profiles[%s] done: %d/%d, cost=%s", campaign, done, len(usernames), cost)
        return {"status": "success", "done": done}
    except (ApifyError, httpx.HTTPError) as exc:
        log.error("Profiles[%s] failed: %s", campaign, exc)
        st.update(status="failed", message=f"ดึงรูปโปรไฟล์ล้มเหลว: {_redact(exc)}",
                  finished_at=dt.datetime.now(config.TZ).isoformat())
        return {"status": "failed", "error": _redact(exc)}
    except Exception as exc:  # noqa: BLE001
        log.exception("Profiles[%s] crashed", campaign)
        st.update(status="failed", message=f"ผิดพลาด: {_redact(exc)}",
                  finished_at=dt.datetime.now(config.TZ).isoformat())
        return {"status": "failed", "error": _redact(exc)}


_PLATFORM_LABELS = {"tiktok": "TikTok", "facebook": "Facebook", "instagram": "Instagram",
                    "youtube": "YouTube", "x": "X", "line": "LINE", "other": "อื่นๆ"}


def refresh_report(campaign: str = "pao") -> dict:
    """Refresh one campaign across ALL platforms each KOL posted on. For every
    KOL link we scrape the matching platform (TikTok/Facebook full; Instagram/
    YouTube/X best-effort) and store one report_posts row per platform, so stats
    stay separated. Never raises — records the outcome in state_for(campaign)."""
    st = state_for(campaign)
    st.update(status="running", message="กำลังดึงข้อมูลจาก Apify…",
              started_at=dt.datetime.now(config.TZ).isoformat(), finished_at=None,
              posts=0, cost_usd=None)
    try:
        with session_scope() as session:
            kols = session.scalars(select(ReportKol).where(
                ReportKol.active.is_(True), ReportKol.campaign == campaign)).all()
            roster = [(k.username.strip().lower(), kol_links(k)) for k in kols]
        st["kol_count"] = len(roster)
        if not roster:
            st.update(status="failed",
                      message="ยังไม่มี KOL ที่ติ๊ก active ในแคมเปญนี้ — เพิ่มในหน้าแก้ไข KOL ก่อน",
                      finished_at=dt.datetime.now(config.TZ).isoformat())
            return {"status": "skipped", "reason": "no active KOLs"}

        # group post URLs by platform (dedup)
        urls_by_plat: Dict[str, list] = {}
        for _u, links in roster:
            for ln in links:
                bucket = urls_by_plat.setdefault(ln["platform"], [])
                if ln["url"] not in bucket:
                    bucket.append(ln["url"])

        cost = 0.0
        partial = False
        scrape_errors: List[str] = []
        profile: Dict[str, Dict] = {}          # tiktok/fb: handle -> {followers,nick}
        index: Dict[str, Dict[str, Dict]] = {}  # platform -> handle -> best post

        def _scrape(plat: str, urls: list):
            nonlocal cost, partial
            if plat == "tiktok":
                items, meta = run_scrape_posts(urls, tolerate_failure=True)
                posts, pr = _parse_report_items(items); profile.update(pr)
            elif plat == "facebook":
                items, meta = run_scrape_fb(urls, tolerate_failure=True)
                posts, pr = _parse_fb_items(items); profile.update(pr)
            elif plat == "instagram":
                items, meta = run_scrape_ig(urls, tolerate_failure=True); posts = _parse_ig_items(items)
            elif plat == "youtube":
                items, meta = run_scrape_yt(urls, tolerate_failure=True); posts = _parse_yt_items(items)
            elif plat == "x":
                items, meta = run_scrape_x(urls, tolerate_failure=True); posts = _parse_x_items(items)
            else:
                return  # line / other → link only, no scrape
            if meta.get("cost_usd"):
                cost += meta["cost_usd"]
            if meta.get("partial"):
                partial = True
            idx = index.setdefault(plat, {})
            for p in posts:
                h = (p.get("username") or "").lower()
                if h and (h not in idx or p["views"] > idx[h]["views"]):
                    idx[h] = p

        for plat, urls in urls_by_plat.items():
            if plat in ("line", "other") or not urls:
                continue
            try:
                _scrape(plat, urls)
            except (ApifyError, httpx.HTTPError) as exc:
                log.error("Refresh[%s] %s failed: %s", campaign, plat, exc)
                scrape_errors.append(f"{_PLATFORM_LABELS.get(plat, plat)}: {_redact(exc)}")

        # match each KOL link back to a scraped post by that platform's handle
        rows = []
        refreshed_users = set()
        plat_counts: Dict[str, int] = {}
        for uname, links in roster:
            for ln in links:
                post = (index.get(ln["platform"]) or {}).get(ln["handle"])
                if post:
                    rows.append((uname, ln["platform"], post, ln["url"]))
                    refreshed_users.add(uname)
                    plat_counts[ln["platform"]] = plat_counts.get(ln["platform"], 0) + 1

        with session_scope() as session:
            if refreshed_users:
                session.execute(delete(ReportPost).where(
                    ReportPost.campaign == campaign, ReportPost.username.in_(refreshed_users)))
            for uname, plat, post, link_url in rows:
                session.add(ReportPost(
                    campaign=campaign, username=uname, platform=plat,
                    video_id=f"{campaign}_{plat}_{post['video_id']}"[:64],
                    url=post.get("url") or link_url, cover_url=post.get("cover_url"),
                    avatar_url=post.get("avatar_url"), posted_at=post.get("posted_at"),
                    views=post["views"], likes=post["likes"], comments=post["comments"],
                    shares=post["shares"], saves=post["saves"],
                ))
            kmap = {u: links for u, links in roster}
            for k in session.scalars(select(ReportKol).where(ReportKol.campaign == campaign)).all():
                for ln in kmap.get(k.username.lower(), []):
                    pr = profile.get(ln["handle"])
                    if pr:
                        if pr.get("followers"):
                            k.followers = pr["followers"]
                        if pr.get("nick") and (not k.display or k.display == k.username):
                            k.display = pr["nick"]
                    post = (index.get(ln["platform"]) or {}).get(ln["handle"])
                    if post and post.get("avatar_url"):
                        k.avatar_url = post["avatar_url"]

        n_posts = len(rows)
        if scrape_errors and n_posts == 0:
            joined = " · ".join(scrape_errors)
            if "401" in joined:
                fail_msg = ("⚠️ Apify token ใช้ไม่ได้/หมดอายุ (401) — ไปที่เมนู Apify Token "
                            "(หน้า Home) ใส่ token ใหม่แล้วลอง Refresh อีกครั้ง")
            else:
                fail_msg = "ดึงข้อมูลไม่สำเร็จ: " + joined
            st.update(status="failed", message=fail_msg,
                      finished_at=dt.datetime.now(config.TZ).isoformat())
            return {"status": "failed", "errors": scrape_errors}

        breakdown = " · ".join(f"{_PLATFORM_LABELS.get(p, p)} {c}"
                               for p, c in plat_counts.items()) or "—"
        msg = f"อัปเดต {n_posts} โพสต์ จาก {len(refreshed_users)}/{len(roster)} KOL · {breakdown}"
        if partial:
            msg += " ⚠️ บางลิงก์ล้มเหลวบางส่วน แต่เก็บข้อมูลที่ดึงได้แล้ว"
        if scrape_errors:
            msg += " · " + " · ".join(scrape_errors)
        try:
            from app.settings import add_cost
            add_cost(campaign, cost)
        except Exception as exc:  # noqa: BLE001 — cost tracking must not break refresh
            log.warning("add_cost failed: %s", exc)
        st.update(status="success", message=msg,
                  finished_at=dt.datetime.now(config.TZ).isoformat(),
                  posts=n_posts, cost_usd=round(cost, 4) if cost else None)
        log.info("Refresh[%s] done: %d posts, %s, cost=%s", campaign, n_posts, breakdown, cost)
        return {"status": "success", "posts": n_posts, "cost_usd": round(cost, 4) if cost else None}

    except (ApifyError, httpx.HTTPError) as exc:
        log.error("Refresh[%s] failed: %s", campaign, exc)
        st.update(status="failed", message=f"ดึงข้อมูลล้มเหลว: {_redact(exc)}",
                  finished_at=dt.datetime.now(config.TZ).isoformat())
        return {"status": "failed", "error": _redact(exc)}
    except Exception as exc:  # noqa: BLE001
        log.exception("Refresh[%s] crashed", campaign)
        st.update(status="failed", message=f"ผิดพลาด: {_redact(exc)}",
                  finished_at=dt.datetime.now(config.TZ).isoformat())
        return {"status": "failed", "error": _redact(exc)}
