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

import httpx
from sqlalchemy import delete, select

from app import config
from app.apify_client import ApifyError, run_scrape_fb, run_scrape_posts, run_scrape_profiles
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


def refresh_report(campaign: str = "pao") -> dict:
    """Refresh one campaign: scrape posts by URL AND refresh every KOL's profile
    picture + followers in the same run (the single Refresh Data button does
    both). Never raises — records the outcome in state_for(campaign)."""
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
            roster = [(k.username.strip().lower(), k.url, k.content_group) for k in kols]
        usernames = {u for u, _, _ in roster}
        urls = [url for _, url, _ in roster if url]
        # TikTok handles (skip Facebook pages) for the profile-picture pass
        profile_handles = [u for u, url, g in roster if g != "Facebook" and not is_fb(url)]
        st["kol_count"] = len(roster)

        if not roster:
            st.update(status="failed",
                      message="ยังไม่มี KOL ที่ติ๊ก active ในแคมเปญนี้ — เพิ่มในหน้าแก้ไข KOL ก่อน",
                      finished_at=dt.datetime.now(config.TZ).isoformat())
            return {"status": "skipped", "reason": "no active KOLs"}

        tt_urls = [u for u in urls if not is_fb(u)]
        fb_urls = [u for u in urls if is_fb(u)]
        log.info("Refresh[%s]: %d TikTok + %d Facebook URLs, %d profiles",
                 campaign, len(tt_urls), len(fb_urls), len(profile_handles))

        # --- posts: each scraper runs independently and tolerates a failed run,
        # so one bad post link never discards the rest of the batch. ---
        posts, profile, cost = [], {}, 0.0
        scrape_errors: List[str] = []
        partial = False
        if tt_urls:
            try:
                items, meta = run_scrape_posts(tt_urls, tolerate_failure=True)
                p, pr = _parse_report_items(items)
                posts += p; profile.update(pr)
                if meta.get("cost_usd"):
                    cost += meta["cost_usd"]
                if meta.get("partial"):
                    partial = True
            except (ApifyError, httpx.HTTPError) as exc:
                log.error("Refresh[%s] TikTok batch failed: %s", campaign, exc)
                scrape_errors.append(f"TikTok: {_redact(exc)}")
        if fb_urls:
            try:
                items, meta = run_scrape_fb(fb_urls, tolerate_failure=True)
                p, pr = _parse_fb_items(items)
                posts += p; profile.update(pr)
                if meta.get("cost_usd"):
                    cost += meta["cost_usd"]
                if meta.get("partial"):
                    partial = True
            except (ApifyError, httpx.HTTPError) as exc:
                log.error("Refresh[%s] Facebook batch failed: %s", campaign, exc)
                scrape_errors.append(f"Facebook: {_redact(exc)}")

        by_user: Dict[str, Dict] = {}
        for p in posts:
            u = p["username"]
            if u in usernames and (u not in by_user or p["views"] > by_user[u]["views"]):
                by_user[u] = p

        with session_scope() as session:
            # Only replace posts for usernames we actually got data for, so a
            # KOL whose link failed keeps its previous snapshot instead of
            # being blanked out.
            refreshed_users = set(by_user)
            if refreshed_users:
                session.execute(delete(ReportPost).where(
                    ReportPost.campaign == campaign, ReportPost.username.in_(refreshed_users)))
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

        # --- profile pictures + followers for ALL active TikTok handles, so
        # every KOL's avatar updates on each refresh (not only those with posts). ---
        prof_done = 0
        try:
            pres = _scrape_and_apply_profiles(campaign, profile_handles)
            prof_done = pres["done"]
            cost += pres["cost"]
        except (ApifyError, httpx.HTTPError) as exc:
            log.error("Refresh[%s] profile pass failed: %s", campaign, exc)
            scrape_errors.append(f"โปรไฟล์: {_redact(exc)}")

        seen = set(by_user)
        # Hard failure only if nothing at all was salvaged (posts AND profiles).
        if scrape_errors and not seen and prof_done == 0:
            joined = " · ".join(scrape_errors)
            if "401" in joined:
                fail_msg = ("⚠️ Apify token ใช้ไม่ได้/หมดอายุ (401) — ไปที่เมนู "
                            "Apify Token (หน้า Home) ใส่ token ใหม่แล้วลอง Refresh อีกครั้ง")
            else:
                fail_msg = "ดึงข้อมูลไม่สำเร็จ: " + joined
            st.update(status="failed", message=fail_msg,
                      finished_at=dt.datetime.now(config.TZ).isoformat())
            return {"status": "failed", "errors": scrape_errors}

        missing = len(usernames) - len(seen)
        if urls:
            msg = f"อัปเดตแล้ว {len(seen)}/{len(usernames)} โพสต์ · รูปโปรไฟล์ {prof_done} ราย"
            if missing > 0:
                msg += f" (ดึงโพสต์ไม่ได้ {missing} — ลิงก์อาจผิด/โพสต์ถูกลบ)"
        else:
            msg = f"อัปเดตรูปโปรไฟล์ {prof_done} ราย (ยังไม่มีลิงก์โพสต์ — ใส่ลิงก์เพื่อดึงสถิติโพสต์)"
        if partial:
            msg += " ⚠️ บางลิงก์ทำให้รอบดึงล้มเหลวบางส่วน แต่ระบบเก็บข้อมูลที่ดึงได้แล้ว"
        if scrape_errors:
            msg += " · " + " · ".join(scrape_errors)
        try:
            from app.settings import add_cost
            add_cost(campaign, cost)
        except Exception as exc:  # noqa: BLE001 — cost tracking must not break refresh
            log.warning("add_cost failed: %s", exc)
        st.update(status="success", message=msg,
                  finished_at=dt.datetime.now(config.TZ).isoformat(),
                  posts=len(seen), cost_usd=round(cost, 4) if cost else None)
        log.info("Refresh[%s] done: %d/%d posts, %d profiles, cost=%s",
                 campaign, len(seen), len(usernames), prof_done, cost)
        return {"status": "success", "posts": len(seen), "profiles": prof_done,
                "cost_usd": round(cost, 4) if cost else None}

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
