"""Refresh the report dataset on demand (the 'Refresh Data' button).

Scrapes the trailing 7-day window via Apify for ONLY the active (ticked)
report_kols, then replaces their rows in report_posts and updates follower
counts. Runs in a background task; progress is exposed via REFRESH_STATE.
"""
from __future__ import annotations

import datetime as dt
import hashlib
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
    run_scrape_fb_pages,
    run_scrape_fb_reels,
    run_scrape_ig,
    run_scrape_ig_profiles,
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
    """Classify a post URL into a platform key. Any real URL that isn't a known
    social platform is treated as a Website (advertorials on media sites, etc.)."""
    u = (url or "").lower()
    if not u.strip():
        return "other"
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
    if u.startswith(("http://", "https://")) or "www." in u or "." in u:
        return "website"
    return "other"


# Generic path segments that are NOT account handles.
_FB_SKIP = {"story.php", "permalink.php", "profile.php", "watch", "reel", "share",
            "photo", "video", "groups", "events", "media", "pages", "p",
            "login", "login.php", "l.php", "sharer", "sharer.php", "home.php",
            "hashtag", "help", "privacy", "policies", "people", "public", "stories"}
_IG_SKIP = {"p", "reel", "reels", "tv", "stories", "explore", "accounts"}
_X_SKIP = {"i", "status", "home", "search", "hashtag", "intent", "login"}


def post_id_from_url(platform: str, url: Optional[str]) -> str:
    """The post's own id from its URL — the reliable key to match a scraped post
    back to the link that requested it (works even when the account handle isn't
    in the URL, e.g. IG /reel/<code>, YT /shorts/<id>, X /status/<id>)."""
    import re as _re
    u = url or ""
    if platform == "tiktok":
        m = _re.search(r"/video/(\d+)", u)
    elif platform == "instagram":
        m = _re.search(r"/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)", u)
    elif platform == "youtube":
        m = _re.search(r"(?:shorts/|v=|youtu\.be/)([A-Za-z0-9_-]{6,})", u)
    elif platform == "x":
        m = _re.search(r"/status/(\d+)", u)
    elif platform == "facebook":
        m = _re.search(r"(?:/posts/|/videos/|/reel/|story_fbid=|/permalink/)(\d+)", u)
    else:
        m = None
    return m.group(1) if m else ""


def is_profile_link(plat: str, url: Optional[str]) -> bool:
    """True when the URL is a channel/profile page, not a specific post — those
    only identify the KOL and must never be sent to a scraper (wasted credits;
    KOLs that haven't posted yet keep a name-only roster row)."""
    u = url or ""
    if post_id_from_url(plat, u):
        return False
    if plat == "tiktok":
        return bool(re.search(r"tiktok\.com/@[^/?#\s]+/?($|[?#])", u, re.I))
    if plat == "facebook":
        return bool(handle_from_url(u)) and not re.search(
            r"(/posts/|/videos/|/reel|/watch|story_fbid=|/permalink/|/share/|fb\.watch)", u, re.I)
    if plat == "instagram":
        return bool(handle_from_url(u)) and not re.search(r"/(p|reel|reels|tv)/", u, re.I)
    if plat == "youtube":
        return bool(re.search(r"youtube\.com/(@[^/?#\s]+/?($|[?#])|channel/|c/|user/)", u, re.I))
    if plat == "x":
        return bool(handle_from_url(u)) and "/status/" not in u.lower()
    return False


def handle_from_url(url: Optional[str]) -> str:
    """Best-effort account handle from a post URL (for matching scraped posts).
    Skips generic path segments (story.php, /p/, /status, ...) that aren't handles."""
    import re as _re
    u = url or ""
    m = _re.search(r"tiktok\.com/@([^/?#\s]+)", u, _re.I)
    if m:
        return m.group(1).lower()
    m = _re.search(r"(?:facebook\.com|fb\.com)/([^/?#\s]+)", u, _re.I)
    if m and m.group(1).lower() not in _FB_SKIP:
        return m.group(1).lower()
    m = _re.search(r"instagram\.com/([^/?#\s]+)", u, _re.I)
    if m and m.group(1).lower() not in _IG_SKIP:
        return m.group(1).lower()
    m = _re.search(r"(?:x\.com|twitter\.com)/([^/?#\s]+)", u, _re.I)
    if m and m.group(1).lower() not in _X_SKIP:
        return m.group(1).lower()
    m = _re.search(r"youtube\.com/@([^/?#\s]+)", u, _re.I)
    if m:
        return m.group(1).lower()
    return ""


def _needs_resolve(url: Optional[str]) -> bool:
    """Short/share links whose canonical URL (with post id / page name) is hidden
    behind a redirect."""
    u = (url or "").lower()
    return ("vt.tiktok.com" in u or "vm.tiktok.com" in u or "/share/" in u
            or "fb.watch" in u or "story.php" in u or "l.facebook.com" in u)


def _resolve_link(url: str) -> str:
    """Follow the redirect of a short/share link to its canonical URL. FB share
    links dead-end at a login wall, so also dig the real post URL out of the
    page's og:url / canonical meta tags (FB embeds them for link previews)."""
    try:
        from app.netguard import is_public_http_url
        if not is_public_http_url(url):  # SSRF guard for team-entered links
            return url
        import httpx as _httpx
        # FB returns HTTP 400 unless the request looks like a real browser
        # navigation (Accept + Sec-Fetch-* headers) — UA alone is not enough,
        # and a failed resolve left /share/ links stuck with zero stats.
        with _httpx.Client(follow_redirects=True, timeout=12, headers={
                "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/125.0.0.0 Safari/537.36"),
                "Accept": ("text/html,application/xhtml+xml,application/xml;"
                           "q=0.9,image/avif,image/webp,*/*;q=0.8"),
                "Accept-Language": "en-US,en;q=0.9,th;q=0.8",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Upgrade-Insecure-Requests": "1"}) as c:
            r = c.get(url)
            final = str(r.url) or url
            low = final.lower()
            if "/share/" not in low and "login" not in low and "checkpoint" not in low:
                return final
            html = r.text or ""
            for pat in (r'rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']',
                        r'property=["\']og:url["\'][^>]*content=["\']([^"\']+)["\']',
                        r'"canonical_url":"([^"]+)"'):
                m = re.search(pat, html, re.I)
                if m:
                    cand = m.group(1).replace("\\/", "/").replace("&amp;", "&")
                    if "facebook.com" in cand and "/share/" not in cand:
                        return cand
            return final
    except Exception:  # noqa: BLE001 — keep the original url on any failure
        return url


def kol_links(k) -> list:
    """All (platform,url,handle) links for a KOL — from links_json, else the
    single url column (pre-multiplatform data)."""
    raw = getattr(k, "links_json", None)
    if raw:
        try:
            out = []
            seen = set()
            for ln in json.loads(raw):
                url = (ln.get("url") or "").strip()
                if not url:
                    continue
                plat = ln.get("platform") or platform_of(url)
                # Dedupe by (platform, post id) — the same post often appears
                # twice in a sheet with different tracking query strings, which
                # duplicated every row/stat in the report.
                key = (plat, post_id_from_url(plat, url)
                       or url.split("?")[0].rstrip("/").lower())
                if key in seen:
                    continue
                seen.add(key)
                d = {
                    "platform": plat,
                    "url": url,
                    "handle": (ln.get("handle") or handle_from_url(url) or k.username).lower(),
                }
                # per-link follower count (filled by refresh from the FB-page /
                # IG-profile scrape) — carried through so the report can show
                # each platform's own audience size
                if _to_int(ln.get("followers")):
                    d["followers"] = _to_int(ln.get("followers"))
                out.append(d)
            if out:
                return out
        except Exception:  # noqa: BLE001 — malformed json falls back to url
            pass
    if k.url:
        return [{"platform": platform_of(k.url), "url": k.url,
                 "handle": (handle_from_url(k.url) or k.username).lower()}]
    return []


def _txt(v) -> str:
    """Coerce an actor text field to a plain string. Some FB item shapes (video
    share links) return message/caption as {'text': ..., 'ranges': [...]} dicts —
    slicing those crashed the whole refresh (unhashable type: 'slice')."""
    if isinstance(v, dict):
        v = v.get("text") or v.get("value") or ""
    if isinstance(v, (list, tuple)):
        v = " ".join(str(x) for x in v if x)
    return v if isinstance(v, str) else ("" if v is None else str(v))


def _first_num(it: dict, keys) -> int:
    """First non-zero numeric value across candidate field names. Sums a dict
    value (e.g. a reactions breakdown {like:.., love:..}). Robust to the many
    field names different Apify actors use for the same metric."""
    for k in keys:
        v = it.get(k)
        if isinstance(v, dict):
            s = sum(_to_int(x) for x in v.values())
            if s:
                return s
        elif v not in (None, "", 0, "0"):
            n = _to_int(v)
            if n:
                return n
    return 0


_IG_VIEWS = ["videoViewCount", "videoPlayCount", "viewCount", "playCount", "igPlayCount",
             "viewsCount", "views", "video_play_count", "video_view_count",
             "ig_play_count", "reelPlayCount", "playsCount", "videoViews"]
_IG_LIKES = ["likesCount", "likeCount", "likes"]
_IG_CMTS = ["commentsCount", "commentCount", "comments"]


def _parse_ig_items(items):
    posts = []
    for it in items:
        handle = (it.get("ownerUsername") or "").strip().lower()
        vid = str(it.get("shortCode") or it.get("id") or "")  # shortCode = URL key
        if not vid:
            continue
        sc = it.get("shortCode")
        posts.append({
            "username": handle, "video_id": vid,
            "url": it.get("url") or (f"https://www.instagram.com/p/{sc}/" if sc else None),
            "caption": _txt(it.get("caption"))[:2000] or None,
            "cover_url": it.get("displayUrl") or it.get("thumbnailUrl"), "avatar_url": None,
            "posted_at": _parse_posted_at(it.get("timestamp")),
            "views": _first_num(it, _IG_VIEWS), "likes": _first_num(it, _IG_LIKES),
            "comments": _first_num(it, _IG_CMTS), "shares": 0,
            "saves": _first_num(it, ["savesCount", "saveCount"]),
        })
    return posts


_YT_VIEWS = ["viewCount", "views", "numberOfViews", "viewCountInt"]
_YT_LIKES = ["likes", "likeCount", "numberOfLikes"]
_YT_CMTS = ["commentsCount", "commentCount", "numberOfComments"]


def _parse_yt_items(items):
    posts = []
    for it in items:
        handle = (it.get("channelName") or it.get("channelUsername") or "").strip().lstrip("@").lower()
        vid = str(it.get("id") or it.get("videoId") or "")
        if not vid:
            continue
        posts.append({
            "username": handle, "video_id": vid, "url": it.get("url"),
            "caption": _txt(it.get("title"))[:2000] or None,
            "cover_url": it.get("thumbnailUrl") or it.get("thumbnail"), "avatar_url": None,
            "posted_at": _parse_posted_at(it.get("date") or it.get("uploadDate")),
            "views": _first_num(it, _YT_VIEWS), "likes": _first_num(it, _YT_LIKES),
            "comments": _first_num(it, _YT_CMTS), "shares": 0, "saves": 0,
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
            "caption": _txt(it.get("text") or it.get("fullText"))[:2000] or None,
            "cover_url": None, "avatar_url": au.get("profilePicture"),
            "posted_at": _parse_posted_at(it.get("createdAt")),
            "views": _first_num(it, ["viewCount", "views", "viewsCount"]),
            "likes": _first_num(it, ["likeCount", "favoriteCount", "likes"]),
            "comments": _first_num(it, ["replyCount", "replies", "commentCount"]),
            "shares": _first_num(it, ["retweetCount", "retweets", "shareCount", "quoteCount"]),
            "saves": _first_num(it, ["bookmarkCount", "bookmarks"]),
        })
    return posts


def _fb_cover_url(it: dict, user: dict) -> Optional[str]:
    """The post's own IMAGE, wherever the FB actor put it (photo posts, albums
    and videos all use different shapes). Must be an actual image file (fbcdn/
    scontent) — facebook.com PAGE links (media[].url points at the photo
    viewer page, not the file) are rejected. Profile pic only as last resort."""
    def _is_img(v) -> bool:
        if not (isinstance(v, str) and v.startswith("http")):
            return False
        # page/permalink URLs live on facebook.com — real images are on the CDN
        return "facebook.com/" not in v.split("//", 1)[-1].split("?")[0]

    def pick(v):
        if _is_img(v):
            return v
        if isinstance(v, dict):
            for kk in ("thumbnail", "thumbnailUrl", "uri", "src", "photo_image",
                       "image", "preferred_thumbnail", "url"):
                r = pick(v.get(kk))
                if r:
                    return r
        return None

    for key in ("thumbnailUrl", "previewImage", "fullPicture", "full_picture",
                "imageUrl", "photoUrl", "image", "picture", "photo"):
        r = pick(it.get(key))
        if r:
            return r
    media = it.get("media")
    if isinstance(media, list):
        for m in media:
            r = pick(m)
            if r:
                return r
    atts = it.get("attachments")
    if isinstance(atts, list):
        for a in atts:
            r = pick(a)
            if r:
                return r
    elif isinstance(atts, dict):
        r = pick(atts)
        if r:
            return r
    return (user or {}).get("profilePic")


def _is_fb_reel(url: Optional[str]) -> bool:
    u = (url or "").lower()
    return ("facebook.com" in u or "fb.com" in u) and ("/reel/" in u or "/reels/" in u)


_FB_REEL_VIEWS = ["viewsCount", "playCount", "videoViewCount", "playsCount",
                  "views", "plays", "videoPlayCount"]


def _parse_fb_reel_items(items):
    """Parse the Facebook REELS actor output → (posts, profile). Field names
    are probed tolerantly (actor versions differ); views ARE available here."""
    posts, profile = [], {}
    for it in items:
        user = it.get("user") or it.get("author") or {}
        page = (it.get("pageName") or it.get("pageUsername")
                or it.get("profileName") or user.get("name") or "").strip().lower()
        if page:
            profile[page] = {"followers": _first_num(it, ["pageLikes", "pageFollowers", "followers"]),
                             "nick": user.get("name") or it.get("pageName") or it.get("profileName")}
        pid = str(it.get("postId") or it.get("id") or "")
        url = it.get("url") or it.get("facebookUrl") or it.get("topLevelUrl") or ""
        posts.append({
            "username": page,
            "video_id": pid or url[:64] or page or "fbreel",
            "url": url or None,
            "caption": (it.get("text") or it.get("description") or it.get("title") or "")[:2000] or None,
            "cover_url": _fb_cover_url(it, user if isinstance(user, dict) else {}),
            "avatar_url": (user.get("profilePic") or user.get("profilePicture")
                           if isinstance(user, dict) else None),
            "posted_at": _parse_posted_at(it.get("time") or it.get("timestamp")
                                          or it.get("createdAt")),
            "views": _first_num(it, _FB_REEL_VIEWS),
            "likes": _first_num(it, _FB_LIKES),
            "comments": _first_num(it, _FB_CMTS),
            "shares": _first_num(it, _FB_SHARES),
            "saves": 0,
        })
    return posts, profile


# Facebook field names vary a lot across actor versions — try every plausible one.
_FB_VIEWS = ["viewsCount", "videoViewCount", "viewCount", "videoViewsCount", "playCount",
             "videoPlayCount", "views", "videoViews", "videoView"]
_FB_LIKES = ["likes", "likesCount", "reactionsCount", "reactionCount", "reactions",
             "reactionLikeCount", "totalReactionsCount"]
_FB_CMTS = ["comments", "commentsCount", "commentCount"]
_FB_SHARES = ["shares", "sharesCount", "shareCount", "reshareCount"]


def _parse_fb_items(items):
    """Parse Facebook actor items → (posts, profile). Pulls every metric the
    actor exposes (views only for videos; reactions/comments/shares otherwise).
    Matched to the roster by pageName / post id."""
    posts, profile = [], {}
    for it in items:
        try:
            if it.get("error"):  # actor placeholder ("no_items" / private post)
                continue
            page = _txt(it.get("pageName") or it.get("pageUsername")).strip().lower()
            user = it.get("user") or {}
            cover = _fb_cover_url(it, user)
            if page:  # only pages can be matched by handle; keep pageless posts too
                profile[page] = {"followers": _first_num(it, ["pageLikes", "pageFollowers", "followers"]),
                                 "nick": user.get("name") or it.get("pageName")}
            # video-share links come back in a raw GraphQL-ish shape: post id in
            # post_id, caption in message.text, unix creation_time, no metrics
            pid = str(it.get("postId") or it.get("post_id") or "")
            fb_url = _txt(it.get("facebookUrl") or it.get("url"))
            posts.append({
                "caption": _txt(it.get("text") or it.get("message") or it.get("postText")
                                or it.get("content"))[:2000] or None,
                "username": page,
                # raw post id so it matches post_id_from_url('facebook', url) in the
                # index; fall back to the post URL (unique per post) then page name,
                # so two id-less posts never collapse into one index slot
                "video_id": pid or fb_url[:64] or page or "fb",
                "url": fb_url or None,
                "cover_url": cover,
                "avatar_url": user.get("profilePic"),
                "posted_at": _parse_posted_at(it.get("time") or it.get("timestamp")
                                              or it.get("creation_time")),
                "views": _first_num(it, _FB_VIEWS),
                "likes": _first_num(it, _FB_LIKES),
                "comments": _first_num(it, _FB_CMTS),
                "shares": _first_num(it, _FB_SHARES),
                "saves": 0,
            })
        except Exception as exc:  # noqa: BLE001 — one odd item must never kill the batch
            log.warning("Skipping unparsable FB item: %s", exc)
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
            "caption": _txt(it.get("text"))[:2000] or None,
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
            # profiles = TikTok handles only (skip Facebook pages), and only
            # KOLs with at least one real WORK link — never scrape someone who
            # hasn't posted yet (roster-only rows waste Apify credits)
            def _has_work(k) -> bool:
                return any(not is_profile_link(ln["platform"], ln["url"])
                           for ln in kol_links(k))
            usernames = [k.username.strip().lower() for k in kols
                         if k.content_group != "Facebook" and not is_fb(k.url)
                         and _has_work(k)]
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
                    "youtube": "YouTube", "x": "X", "line": "LINE", "website": "Website",
                    "other": "ลิงก์"}


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

        # Resolve short/share links to their canonical URL so post-id / page-name
        # matching works (FB share links, vt.tiktok.com, fb.watch, story.php).
        st.update(message="กำลังตรวจลิงก์…")
        for _u, links in roster:
            for ln in links:
                if _needs_resolve(ln["url"]):
                    final = _resolve_link(ln["url"])
                    if final and final != ln["url"]:
                        ln["url"] = final
                        ln["platform"] = platform_of(final)
                        h = handle_from_url(final)
                        if h:
                            ln["handle"] = h

        cost = 0.0
        partial = False
        scrape_errors: List[str] = []
        profile: Dict[str, Dict] = {}          # tiktok/fb: handle -> {followers,nick}
        index: Dict[str, Dict[str, Dict]] = {}  # platform -> {"id":{}, "handle":{}}
        SCRAPEABLE = ("tiktok", "facebook", "instagram", "youtube", "x")

        def _scrape_platform(plat: str, urls: list):
            """Run the right actor + parser → (posts, meta, profile_dict)."""
            if plat == "tiktok":
                items, meta = run_scrape_posts(urls, tolerate_failure=True)
                posts, pr = _parse_report_items(items); return posts, meta, pr
            if plat == "facebook":
                # Reels go to the dedicated reels actor (posts scraper has no
                # view counts for reels); everything else to the posts actor.
                reels = [u for u in urls if _is_fb_reel(u)]
                normal = [u for u in urls if u not in reels]
                posts, pr = [], {}
                cost_sum, part = 0.0, False
                if normal:
                    items, meta = run_scrape_fb(normal, tolerate_failure=True)
                    p2, pr2 = _parse_fb_items(items)
                    posts += p2; pr.update(pr2)
                    cost_sum += meta.get("cost_usd") or 0.0
                    part = part or bool(meta.get("partial"))
                if reels:
                    items, meta = run_scrape_fb_reels(reels, tolerate_failure=True)
                    p2, pr2 = _parse_fb_reel_items(items)
                    posts += p2; pr.update(pr2)
                    cost_sum += meta.get("cost_usd") or 0.0
                    part = part or bool(meta.get("partial"))
                return posts, {"cost_usd": cost_sum or None, "partial": part}, pr
            if plat == "instagram":
                items, meta = run_scrape_ig(urls, tolerate_failure=True); return _parse_ig_items(items), meta, {}
            if plat == "youtube":
                items, meta = run_scrape_yt(urls, tolerate_failure=True); return _parse_yt_items(items), meta, {}
            if plat == "x":
                items, meta = run_scrape_x(urls, tolerate_failure=True); return _parse_x_items(items), meta, {}
            return [], {}, {}

        def _absorb(plat, posts, meta, pr):
            nonlocal cost, partial
            profile.update(pr or {})
            if meta.get("cost_usd"):
                cost += meta["cost_usd"]
            if meta.get("partial"):
                partial = True
            slot = index.setdefault(plat, {"id": {}, "handle": {}})
            for p in posts:
                vid = str(p.get("video_id") or "")
                if vid and (vid not in slot["id"] or p["views"] > slot["id"][vid]["views"]):
                    slot["id"][vid] = p
                h = (p.get("username") or "").lower()
                if h and (h not in slot["handle"] or p["views"] > slot["handle"][h]["views"]):
                    slot["handle"][h] = p

        def _url_key(plat, url):
            """A reliable match key from the URL (post id, or a handle that is IN
            the URL). Empty → 'unkeyable' (e.g. a FB share link) → must be
            scraped on its own and associated directly."""
            return post_id_from_url(plat, url) or handle_from_url(url)

        # batch-scrape the keyable links per platform (cheap, matched by id/handle)
        # — profile/channel links (KOLs who haven't posted yet) are never scraped
        skipped_profiles = 0
        keyable_urls: Dict[str, list] = {}
        for uname, links in roster:
            for ln in links:
                plat = ln["platform"]
                if plat not in SCRAPEABLE:
                    continue
                if is_profile_link(plat, ln["url"]):
                    skipped_profiles += 1
                    continue
                if _url_key(plat, ln["url"]):
                    bucket = keyable_urls.setdefault(plat, [])
                    if ln["url"] not in bucket:
                        bucket.append(ln["url"])

        for plat, urls in keyable_urls.items():
            try:
                _absorb(plat, *_scrape_platform(plat, urls))
            except (ApifyError, httpx.HTTPError) as exc:
                log.error("Refresh[%s] %s batch failed: %s", campaign, plat, exc)
                scrape_errors.append(f"{_PLATFORM_LABELS.get(plat, plat)}: {_redact(exc)}")

        rows = []
        refreshed_users = set()
        plat_counts: Dict[str, int] = {}

        def _add_row(uname, plat, post, ln):
            rows.append((uname, plat, post, ln))  # ln = the roster link dict
            refreshed_users.add(uname)
            plat_counts[plat] = plat_counts.get(plat, 0) + 1

        # match every scrapeable link against the batch results; anything still
        # unmatched (FB share links, page-name mismatch, ...) is scraped alone
        need_single = []
        for uname, links in roster:
            for ln in links:
                plat = ln["platform"]
                if plat not in SCRAPEABLE or is_profile_link(plat, ln["url"]):
                    continue  # profile links are name-only — never scraped
                slot = index.get(plat) or {"id": {}, "handle": {}}
                pid = post_id_from_url(plat, ln["url"])
                post = (slot["id"].get(pid) if pid else None) or slot["handle"].get(handle_from_url(ln["url"]))
                if post:
                    _add_row(uname, plat, post, ln)
                else:
                    need_single.append((uname, ln))

        MAX_SINGLE = 300
        if len(need_single) > MAX_SINGLE:  # surface truncation, never drop silently
            scrape_errors.append(
                f"ลิงก์เจาะจงเกิน {MAX_SINGLE} รายการ — ข้ามไป {len(need_single) - MAX_SINGLE} ลิงก์")
        if need_single:
            st.update(message=f"กำลังดึงลิงก์แบบเจาะจง {min(len(need_single), MAX_SINGLE)} รายการ…")
        for uname, ln in need_single[:MAX_SINGLE]:
            plat = ln["platform"]
            try:
                posts, meta, pr = _scrape_platform(plat, [ln["url"]])
                profile.update(pr or {})
                if meta.get("cost_usd"):
                    cost += meta["cost_usd"]
                if posts:
                    best = max(posts, key=lambda p: (p.get("views", 0) + p.get("likes", 0)))
                    _add_row(uname, plat, best, ln)
                    canon = best.get("url")  # persist canonical URL → keyable next time
                    if canon:
                        ln["url"] = canon
                        ln["platform"] = platform_of(canon)
                        h = handle_from_url(canon)
                        if h:
                            ln["handle"] = h
            except (ApifyError, httpx.HTTPError) as exc:
                log.error("Refresh[%s] %s single failed: %s", campaign, plat, exc)
                scrape_errors.append(f"{_PLATFORM_LABELS.get(plat, plat)}: {_redact(exc)}")

        # FB pages / IG accounts don't expose follower counts on post items —
        # scrape the pages/profiles themselves so ER-by-followers works for
        # photo posts. Only the handles that actually posted are scraped.
        ig_handles = sorted({(post.get("username") or "").lower()
                             for _u, plat, post, _l in rows if plat == "instagram"} - {""})
        fb_pages: Dict[str, str] = {}
        for _u, plat, post, ln in rows:
            if plat != "facebook":
                continue
            h = handle_from_url(ln["url"]) or (post.get("username") or "").lower()
            if h and h not in fb_pages:
                fb_pages[h] = f"https://www.facebook.com/{h}"
        if ig_handles:
            try:
                st.update(message=f"กำลังดึง followers โปรไฟล์ Instagram {len(ig_handles)} บัญชี…")
                items, meta = run_scrape_ig_profiles(ig_handles, tolerate_failure=True)
                if meta.get("cost_usd"):
                    cost += meta["cost_usd"]
                for it in items:
                    h = (it.get("username") or "").lower()
                    if not h:
                        continue
                    d = profile.setdefault(h, {})
                    f = _first_num(it, ["followersCount", "followers"])
                    if f:
                        d["followers"] = f
                    if it.get("fullName") and not d.get("nick"):
                        d["nick"] = it.get("fullName")
                    av = it.get("profilePicUrlHD") or it.get("profilePicUrl")
                    if av and not d.get("avatar"):
                        d["avatar"] = av
            except (ApifyError, httpx.HTTPError) as exc:
                log.error("Refresh[%s] IG profiles failed: %s", campaign, exc)
                scrape_errors.append(f"IG followers: {_redact(exc)}")
        if fb_pages:
            try:
                st.update(message=f"กำลังดึง followers เพจ Facebook {len(fb_pages)} เพจ…")
                items, meta = run_scrape_fb_pages(list(fb_pages.values()), tolerate_failure=True)
                if meta.get("cost_usd"):
                    cost += meta["cost_usd"]
                for it in items:
                    h = (handle_from_url(it.get("pageUrl") or it.get("facebookUrl")
                                         or it.get("url") or "")
                         or (it.get("pageName") or "").strip().lower())
                    if not h:
                        continue
                    f = _first_num(it, ["followers", "followersCount", "followerCount", "likes"])
                    av = it.get("profilePictureUrl") or it.get("profilePhoto") or it.get("pageLogo")
                    for key in {h, (it.get("pageName") or "").strip().lower()} - {""}:
                        d = profile.setdefault(key, {})
                        if f:
                            d["followers"] = f
                        if it.get("title") and not d.get("nick"):
                            d["nick"] = it.get("title")
                        if av and not d.get("avatar"):
                            d["avatar"] = av
            except (ApifyError, httpx.HTTPError) as exc:
                log.error("Refresh[%s] FB pages failed: %s", campaign, exc)
                scrape_errors.append(f"FB followers: {_redact(exc)}")

        # per-KOL followers / nick / avatar aggregated from the matched posts;
        # each link also remembers its own platform's follower count
        followers_by_user, nick_by_user, avatar_by_user = {}, {}, {}
        for uname, plat, post, ln in rows:
            pr = (profile.get((post.get("username") or "").lower())
                  or profile.get(handle_from_url(ln["url"]) or "")
                  or profile.get((ln.get("handle") or "").lower()))
            if pr:
                if pr.get("followers"):
                    followers_by_user.setdefault(uname, pr["followers"])
                    ln["followers"] = pr["followers"]
                if pr.get("nick"):
                    nick_by_user.setdefault(uname, pr["nick"])
                if pr.get("avatar"):
                    avatar_by_user.setdefault(uname, pr["avatar"])
            if post.get("avatar_url"):
                avatar_by_user.setdefault(uname, post["avatar_url"])

        with session_scope() as session:
            if refreshed_users:
                session.execute(delete(ReportPost).where(
                    ReportPost.campaign == campaign, ReportPost.username.in_(refreshed_users)))
            seen_vids = set()
            for uname, plat, post, ln in rows:
                link_url = ln["url"]
                # unique per (campaign, platform, KOL, link) — avoids collisions
                # when a post has no real id (e.g. FB posts fall back to a hash)
                vkey = hashlib.md5((uname + "|" + (link_url or post.get("video_id") or "")).encode()).hexdigest()
                vid = f"{campaign}_{plat}_{vkey}"[:64]
                if vid in seen_vids:  # same KOL pasted the same link twice — skip dup
                    continue
                seen_vids.add(vid)
                session.add(ReportPost(
                    campaign=campaign, username=uname, platform=plat,
                    video_id=vid,
                    url=post.get("url") or link_url, cover_url=post.get("cover_url"),
                    caption=post.get("caption"),
                    avatar_url=post.get("avatar_url"), posted_at=post.get("posted_at"),
                    views=post["views"], likes=post["likes"], comments=post["comments"],
                    shares=post["shares"], saves=post["saves"],
                ))
            kmap = {u: links for u, links in roster}
            for k in session.scalars(select(ReportKol).where(ReportKol.campaign == campaign)).all():
                u = k.username.lower()
                links_now = kmap.get(u)
                if links_now:  # persist resolved canonical URLs so next refresh is fast
                    k.links_json = json.dumps(links_now, ensure_ascii=False)
                if followers_by_user.get(u):
                    k.followers = followers_by_user[u]
                if nick_by_user.get(u) and (not k.display or k.display == k.username):
                    k.display = nick_by_user[u]
                if avatar_by_user.get(u):
                    k.avatar_url = avatar_by_user[u]

        scrape_errors = list(dict.fromkeys(scrape_errors))  # dedup repeats
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
        # platforms that returned data but matched 0 posts → likely actor field
        # mismatch or unresolvable link (surfaced so it can be tuned)
        unmatched = [_PLATFORM_LABELS.get(p, p) for p, s in index.items()
                     if s.get("id") and plat_counts.get(p, 0) == 0]
        msg = f"อัปเดต {n_posts} โพสต์ จาก {len(refreshed_users)}/{len(roster)} KOL · {breakdown}"
        if skipped_profiles:
            msg += f" · ข้าม {skipped_profiles} ลิงก์โปรไฟล์ (ยังไม่มีลิงก์งาน — ไม่เปลือง Apify)"
        if unmatched:
            msg += " · จับคู่ไม่ได้: " + ", ".join(unmatched)
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
