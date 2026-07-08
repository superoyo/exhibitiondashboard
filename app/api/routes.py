"""REST API routers (brief section 10). All endpoints return JSON."""
from __future__ import annotations

import datetime as dt
import hashlib
import logging
import re
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.netguard import is_public_http_url

import json

from app import config, queries
from app.db import db_dependency
from app.models import Campaign, ImageCache, Kol, ReportKol, ReportPost
from app.report_refresh import (
    _PLATFORM_LABELS,
    fetch_profiles,
    kol_links,
    refresh_report,
    state_for,
)
from app.scrape import run_daily_scrape

log = logging.getLogger("api")
router = APIRouter(prefix="/api")


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def auth_login(body: LoginIn):
    """Proxy Wazzup login (avoids browser CORS). Returns only what the client
    session needs — never the password, never hrPassword."""
    from app.auth import wazzup_login
    try:
        d = wazzup_login((body.username or "").strip(), body.password or "")
    except ValueError:
        raise HTTPException(401, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    except RuntimeError:
        raise HTTPException(502, "เข้าสู่ระบบไม่สำเร็จ กรุณาลองใหม่อีกครั้ง")
    keys = ("empThaiName", "empEngName", "nickName", "positionName",
            "departmentName", "profileURL", "email", "access_token", "expiration")
    return {k: d.get(k) for k in keys}


@router.get("/auth/profile")
def auth_profile(authorization: Optional[str] = Header(None)):
    """Proxy Get Profile with the caller's bearer token."""
    from app.auth import wazzup_profile
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        raise HTTPException(401, "missing token")
    data = wazzup_profile(token)
    if data is None:
        raise HTTPException(401, "invalid or expired token")
    return data


@router.get("/health")
def health(session: Session = Depends(db_dependency)):
    run = queries.last_run(session)
    latest = queries.latest_scrape_date(session)
    return {
        "status": "ok",
        "latest_scrape_date": latest.isoformat() if latest else None,
        "last_run": {
            "status": run.status,
            "run_date": run.run_date.isoformat(),
            "posts_count": run.posts_count,
            "cost_usd": float(run.cost_usd) if run.cost_usd is not None else None,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "error": run.error,
        }
        if run
        else None,
    }


@router.get("/summary")
def summary(
    date: str = Query("latest"),
    group: str = Query("all"),
    session: Session = Depends(db_dependency),
):
    resolved = queries.resolve_date(session, date)
    if resolved is None:
        return {"date": None, "kpis": {}, "kols": [], "available_dates": [], "group": group}
    return queries.summary(session, resolved, group)


@router.get("/trend")
def trend(
    metric: str = Query("views"),
    group: str = Query("all"),
    days: int = Query(30, ge=1, le=365),
    split_by_group: bool = Query(False),
    session: Session = Depends(db_dependency),
):
    if split_by_group:
        return queries.trend_by_group(session, metric, days)
    return queries.trend(session, metric, group, days)


@router.get("/posts")
def posts(
    date: str = Query("latest"),
    group: str = Query("all"),
    sort: str = Query("views"),
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(db_dependency),
):
    resolved = queries.resolve_date(session, date)
    if resolved is None:
        return {"date": None, "posts": []}
    return {"date": resolved.isoformat(), "posts": queries.posts_for(session, resolved, group, sort, limit)}


@router.get("/kols/{username}")
def kol_detail(username: str, days: int = Query(30, ge=1, le=365), session: Session = Depends(db_dependency)):
    detail = queries.kol_detail(session, username, days)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"KOL '{username}' not found")
    return detail


@router.post("/scrape/run")
def trigger_scrape(
    background: BackgroundTasks,
    x_admin_key: Optional[str] = Header(None, alias="X-ADMIN-KEY"),
):
    """Manually trigger a scrape (protected by ADMIN_KEY). Runs in background."""
    if not config.ADMIN_KEY or x_admin_key != config.ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-ADMIN-KEY")
    background.add_task(run_daily_scrape)
    return {"status": "accepted", "message": "Scrape started in background", "queued_at": dt.datetime.now(config.TZ).isoformat()}


# ----------------------------------------------------------------------------
# KOL roster editor (open, no auth) — Tracker (`kols`) + Report (`report_kols`)
# Separate /api/roster/* prefix avoids clashing with GET /api/kols/{username}.
# ----------------------------------------------------------------------------

class KolIn(BaseModel):
    username: str
    display: Optional[str] = None
    group: str
    subgroup: Optional[str] = None
    url: Optional[str] = None


class KolPatch(BaseModel):
    display: Optional[str] = None
    group: Optional[str] = None
    subgroup: Optional[str] = None
    active: Optional[bool] = None
    url: Optional[str] = None
    links: Optional[list[dict]] = None  # [{platform,url,handle}] — all channels


def _serialize(k) -> dict:
    out = {
        "id": k.id,
        "username": k.username,
        "display": k.display,
        "group": k.content_group,
        "active": k.active,
    }
    if hasattr(k, "url"):
        out["url"] = k.url
    if hasattr(k, "links_json"):
        out["links"] = kol_links(k)  # [{platform,url,handle}], all platforms
    if hasattr(k, "subgroup"):
        out["subgroup"] = k.subgroup
    return out


def _roster_endpoints(model, is_report: bool):
    """Build a list/add/update/delete handler set bound to one ORM model.
    Report rosters are scoped by ?campaign= (default 'pao')."""

    def list_all(campaign: str = "pao", session: Session = Depends(db_dependency)):
        q = select(model)
        if is_report:
            q = q.where(model.campaign == campaign)
            q = q.order_by(model.sort_order, model.id)  # source-file order
        else:
            q = q.order_by(model.content_group, model.username)
        rows = session.scalars(q).all()
        return {"kols": [_serialize(k) for k in rows]}

    def add(body: KolIn, campaign: str = "pao", session: Session = Depends(db_dependency)):
        username = (body.username or "").strip().lstrip("@").lower()
        if not username:
            raise HTTPException(400, "username ห้ามว่าง")
        dup = select(model).where(model.username == username)
        if is_report:
            dup = dup.where(model.campaign == campaign)
        if session.scalar(dup):
            raise HTTPException(409, f"มี @{username} อยู่แล้ว")
        k = model(
            username=username,
            display=(body.display or username).strip(),
            content_group=body.group.strip(),
            active=True,
        )
        if is_report:
            k.campaign = campaign
            k.sort_order = (session.scalar(
                select(func.max(model.sort_order)).where(model.campaign == campaign)) or 0) + 1
            if body.subgroup is not None:
                k.subgroup = body.subgroup.strip() or None
            if body.url:
                k.url = body.url.strip()
        session.add(k)
        try:
            session.commit()
        except IntegrityError:  # concurrent add of the same username → 409, not 500
            session.rollback()
            raise HTTPException(409, f"มี @{username} อยู่แล้ว")
        session.refresh(k)
        return _serialize(k)

    def update(item_id: int, body: KolPatch, session: Session = Depends(db_dependency)):
        k = session.get(model, item_id)
        if not k:
            raise HTTPException(404, "ไม่พบ KOL")
        if body.display is not None:
            k.display = body.display.strip()
        if body.group is not None:
            k.content_group = body.group.strip()
        if body.active is not None:
            k.active = body.active
        if is_report and body.subgroup is not None:
            k.subgroup = body.subgroup.strip() or None
        if is_report and body.links is not None:
            links = [{"platform": (l.get("platform") or ""), "url": (l.get("url") or "").strip(),
                      "handle": (l.get("handle") or "")}
                     for l in body.links if (l.get("url") or "").strip()]
            k.links_json = json.dumps(links, ensure_ascii=False) if links else None
            k.url = links[0]["url"] if links else None
        elif is_report and body.url is not None:
            k.url = body.url.strip()
        session.commit()
        session.refresh(k)
        return _serialize(k)

    def delete(item_id: int, session: Session = Depends(db_dependency)):
        k = session.get(model, item_id)
        if not k:
            raise HTTPException(404, "ไม่พบ KOL")
        session.delete(k)
        session.commit()
        return {"status": "deleted", "id": item_id}

    return list_all, add, update, delete


for _name, _model, _isrep in (("tracker", Kol, False), ("report", ReportKol, True)):
    _list, _add, _update, _delete = _roster_endpoints(_model, _isrep)
    router.add_api_route(f"/roster/{_name}", _list, methods=["GET"])
    router.add_api_route(f"/roster/{_name}", _add, methods=["POST"])
    router.add_api_route(f"/roster/{_name}/{{item_id}}", _update, methods=["PATCH"])
    router.add_api_route(f"/roster/{_name}/{{item_id}}", _delete, methods=["DELETE"])


# ----------------------------------------------------------------------------
# Bulk import — REPLACE a campaign's whole roster from a parsed KOL list
# (Excel/CSV or Google Sheet, parsed client-side). Replace, never append, so a
# re-upload can't create duplicate rows.
# ----------------------------------------------------------------------------

class BulkLinkIn(BaseModel):
    platform: Optional[str] = None
    url: str
    handle: Optional[str] = None


class BulkKolIn(BaseModel):
    username: str
    display: Optional[str] = None
    group: Optional[str] = None
    subgroup: Optional[str] = None
    url: Optional[str] = None
    links: Optional[list[BulkLinkIn]] = None
    followers: Optional[int] = 0


class BulkRosterIn(BaseModel):
    kols: list[BulkKolIn]
    sheet_url: Optional[str] = None  # remember the source Google Sheet for re-sync


@router.post("/roster/report/bulk")
def bulk_replace_report(body: BulkRosterIn, campaign: str = "pao",
                        session: Session = Depends(db_dependency)):
    """Replace ALL KOLs of one campaign with the given list (dedup by username).
    Each KOL may carry multiple platform links (links_json). report_posts are
    left for the next Refresh to re-match."""
    seen: dict = {}
    for k in body.kols:
        u = (k.username or "").strip().lstrip("@").lower()
        if u:
            seen[u] = k  # last wins
    if not seen:
        raise HTTPException(400, "ไม่พบรายชื่อ KOL ที่ใช้ได้ในไฟล์/ชีต")

    session.execute(delete(ReportKol).where(ReportKol.campaign == campaign))
    for i, (u, k) in enumerate(seen.items()):
        links = [{"platform": (ln.platform or ""), "url": ln.url.strip(),
                  "handle": (ln.handle or "")} for ln in (k.links or []) if ln.url and ln.url.strip()]
        primary = (k.url.strip() if k.url else "") or (links[0]["url"] if links else "")
        session.add(ReportKol(
            sort_order=i,  # keep the source file's row order
            username=u,
            display=(k.display or u).strip(),
            content_group=(k.group or "KOL").strip() or "KOL",
            subgroup=(k.subgroup.strip() if k.subgroup else None) or None,
            campaign=campaign,
            url=primary or None,
            links_json=json.dumps(links, ensure_ascii=False) if links else None,
            followers=int(k.followers or 0),
            active=True,
        ))
    session.commit()
    if body.sheet_url is not None:
        from app.settings import set_setting
        set_setting(f"sheet_url:{campaign}", body.sheet_url.strip())
    return {"status": "replaced", "count": len(seen)}


@router.get("/roster/report/sheet")
def get_report_sheet(campaign: str = "pao"):
    """The Google Sheet URL last imported for this campaign (for re-sync)."""
    from app.settings import get_setting
    return {"url": get_setting(f"sheet_url:{campaign}") or ""}


def _to_download_url(u: str) -> str:
    """Turn a share link from various hosts into a direct file-download URL so
    the browser can parse it. Supports Google Sheets/Drive, OneDrive/SharePoint,
    Dropbox; otherwise assumes the URL is already a direct file link."""
    low = u.lower()
    m = re.search(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9-_]+)", u)
    if m:
        return f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=xlsx"
    m = (re.search(r"drive\.google\.com/(?:file/d/|open\?id=|uc\?id=)([a-zA-Z0-9-_]+)", u)
         or re.search(r"drive\.google\.com/.*[?&]id=([a-zA-Z0-9-_]+)", u))
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
    if "dropbox.com" in low:
        base = u.split("?")[0]
        return base + "?dl=1"
    if "sharepoint.com" in low or "1drv.ms" in low or "onedrive.live.com" in low:
        return u + ("&download=1" if "?" in u else "?download=1")
    return u  # assume a direct .xlsx/.csv URL


@router.get("/sheet/fetch")
def sheet_fetch(url: str = Query(...)):
    """Proxy a public spreadsheet from an online host (Google Sheet/Drive,
    OneDrive/SharePoint, Dropbox, or a direct file link) so the browser can
    parse it (client-side fetch is blocked by CORS). Returns the raw bytes."""
    dl = _to_download_url(url.strip())
    if not is_public_http_url(dl):  # SSRF guard
        raise HTTPException(400, "ลิงก์ไฟล์ไม่ถูกต้อง")
    try:
        import httpx as _httpx
        r = _httpx.get(dl, timeout=45, follow_redirects=True, headers={
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/125.0.0.0 Safari/537.36")})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"ดึงไฟล์ไม่สำเร็จ: {exc}")
    ctype = (r.headers.get("content-type") or "").lower()
    if r.status_code != 200:
        raise HTTPException(400, "ดึงไฟล์ไม่สำเร็จ — ตรวจว่าตั้งแชร์เป็น 'ใครก็ตามที่มีลิงก์ (ผู้อ่าน)'")
    # An HTML page means we hit a login/preview wall, not the actual file
    if "html" in ctype and b"<html" in (r.content[:1024].lower()):
        raise HTTPException(
            400, "ลิงก์นี้ยังเปิด public ไม่ได้ (เจอหน้า login/พรีวิว) — ตั้งแชร์เป็น 'ใครก็ตามที่มีลิงก์ ผู้อ่าน' ก่อน")
    return Response(content=r.content, media_type="application/octet-stream")


# ----------------------------------------------------------------------------
# Resolve the posting account's @handle from a post link — used by bulk import
# when a row has a post URL but no username (incl. vt.tiktok.com short links).
# Uses redirect-following + page HTML, no Apify credits.
# ----------------------------------------------------------------------------

_RE_TT = re.compile(r"tiktok\.com/@([^/?#\s]+)", re.I)
_RE_FB = re.compile(r"(?:facebook\.com|fb\.com)/([^/?#\s]+)", re.I)
_RE_IG = re.compile(r"instagram\.com/([^/?#\s]+)", re.I)
_RE_UNIQ = re.compile(r'"uniqueId":"([^"]+)"')
_FB_SKIP = {"watch", "story.php", "permalink.php", "profile.php", "share", "reel",
            "photo", "video", "login", "login.php", "l.php", "sharer", "sharer.php",
            "home.php", "hashtag", "help", "privacy", "policies", "people", "public"}


def _handle_from_url(s: str) -> str:
    m = _RE_TT.search(s or "")
    if m:
        return m.group(1).lower()
    m = _RE_FB.search(s or "")
    if m and m.group(1).lower() not in _FB_SKIP:
        return m.group(1).lower()
    m = _RE_IG.search(s or "")
    if m:
        return m.group(1).lower()
    return ""


def _handle_from_html(html: str) -> str:
    m = _RE_UNIQ.search(html or "")
    if m:
        return m.group(1).lower()
    m = _RE_TT.search(html or "")
    if m:
        return m.group(1).lower()
    return ""


class ResolveIn(BaseModel):
    urls: list[str]


@router.post("/resolve-handles")
def resolve_handles(body: ResolveIn):
    """Map each post URL -> the posting account's @handle AND the canonical
    final URL (short links like vt.tiktok.com hide whether they're a profile
    or a post — the import needs the resolved URL to tell them apart).
    Hard 90s total budget so one request can't pin a worker for an hour."""
    import time as _time
    urls = [u for u in dict.fromkeys(body.urls) if u][:300]
    out: dict = {}
    resolved: dict = {}
    deadline = _time.monotonic() + 90
    import httpx as _httpx
    headers = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/125.0.0.0 Safari/537.36")}
    with _httpx.Client(follow_redirects=True, timeout=12, headers=headers) as client:
        for u in urls:
            h = _handle_from_url(u)
            final = u
            if not h and _time.monotonic() < deadline and is_public_http_url(u):
                try:
                    r = client.get(u)
                    fin = str(r.url) or u
                    low = fin.lower()
                    if "login" not in low and "checkpoint" not in low:
                        final = fin
                    h = _handle_from_url(final) or _handle_from_html(r.text)
                except Exception:  # noqa: BLE001 — unresolvable links just map to ""
                    h = ""
            out[u] = h
            resolved[u] = final
    return {"handles": out, "resolved": resolved}


@router.get("/scrape/inspect")
def scrape_inspect(url: str = Query(...), platform: str = ""):
    """Debug: run the matching actor on ONE post URL and return the raw item(s)
    so its exact field names can be verified. Costs one small Apify scrape."""
    from app import apify_client as ac
    from app.report_refresh import _needs_resolve, _resolve_link, platform_of
    if _needs_resolve(url):
        url = _resolve_link(url)
    plat = platform or platform_of(url)
    fn = {"tiktok": ac.run_scrape_posts, "facebook": ac.run_scrape_fb,
          "instagram": ac.run_scrape_ig, "youtube": ac.run_scrape_yt,
          "x": ac.run_scrape_x}.get(plat)
    if not fn:
        raise HTTPException(400, f"platform '{plat}' ไม่รองรับการดึง stat")
    try:
        items, meta = fn([url], tolerate_failure=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"scrape failed: {exc}")
    return {
        "resolved_url": url, "platform": plat,
        "meta": {k: meta.get(k) for k in ("status", "partial", "cost_usd")},
        "count": len(items), "items": items[:2],
    }


# ----------------------------------------------------------------------------
# Report data + Refresh Data button (scrape 7-day window for active report KOLs)
# ----------------------------------------------------------------------------

@router.get("/report/data")
def report_data(campaign: str = "pao", session: Session = Depends(db_dependency)):
    """Records for the dynamic report page of one campaign. Includes ALL active
    roster rows (stats 0 if not scraped yet) so the structure shows before links
    are added. `category` = subgroup when present, else the big group; `biggroup`
    is the top-level group (for 2-level grouping)."""
    roster = session.scalars(
        select(ReportKol)
        .where(ReportKol.active.is_(True), ReportKol.campaign == campaign)
        .order_by(ReportKol.sort_order, ReportKol.id)  # source-file order
    ).all()
    # best post per (username, platform) so each platform's stats stay separate
    posts_by: dict = {}
    for p in session.scalars(select(ReportPost).where(ReportPost.campaign == campaign)).all():
        key = (p.username.lower(), p.platform or "tiktok")
        if key not in posts_by or p.views > posts_by[key].views:
            posts_by[key] = p

    records = []
    with_data = 0
    for k in roster:
        links = kol_links(k)
        if not links:
            # linkless KOL: surface its best existing post on ANY platform, so
            # legacy/scraped data still shows instead of a permanent zero row
            cands = [p for (u, _pl), p in posts_by.items() if u == k.username.lower()]
            best = max(cands, key=lambda p: p.views) if cands else None
            links = [{"platform": (best.platform if best else "other"),
                      "url": k.url or "", "handle": k.username.lower()}]
        for ln in links:
            plat = ln["platform"]
            p = posts_by.get((k.username.lower(), plat))
            if p:
                with_data += 1
            records.append({
                "username": k.username,
                "nickname": k.display,
                "platform": plat,
                "platform_label": _PLATFORM_LABELS.get(plat, plat),
                "category": k.subgroup or k.content_group,
                "biggroup": k.content_group,
                # per-platform audience when the refresh captured it (FB page /
                # IG profile scrape) — falls back to the KOL-level count
                "followers": ln.get("followers") or k.followers,
                "views": p.views if p else 0,
                "likes": p.likes if p else 0,
                "comments": p.comments if p else 0,
                "shares": p.shares if p else 0,
                "saves": p.saves if p else 0,
                "posted": (p.posted_at.date().isoformat() if p and p.posted_at else ""),
                "url": ln["url"] or (p.url if p else "") or "",
                "thumb": (p.cover_url if p else "") or "",
                "avatar": (p.avatar_url if p else "") or k.avatar_url or "",
                "has_data": bool(p),
            })
    last = session.scalar(
        select(func.max(ReportPost.scraped_at)).where(ReportPost.campaign == campaign)
    )
    from app.settings import get_cost
    cost = get_cost(campaign)
    return {
        "records": records,
        "refreshed_at": last.isoformat() if last else None,
        "roster_count": len(records),
        "post_count": with_data,
        "kol_count": len(roster),
        "cost_total": cost["total"],
        "cost_count": cost["count"],
    }


@router.get("/report/pptx")
def report_pptx(campaign: str = "pao"):
    """Generate and download the campaign's PowerPoint report."""
    from urllib.parse import quote

    from fastapi.responses import StreamingResponse

    from app.pptx_report import build_pptx
    try:
        buf, fname = build_pptx(campaign)
    except Exception as exc:  # noqa: BLE001
        log.exception("pptx build failed for %s", campaign)
        raise HTTPException(500, f"สร้างไฟล์ PowerPoint ไม่สำเร็จ: {exc}")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"},
    )


@router.post("/report/cost/reset")
def report_cost_reset(campaign: str = "pao"):
    from app.settings import reset_cost
    reset_cost(campaign)
    return {"status": "reset", "campaign": campaign}


@router.post("/report/refresh")
def report_refresh_trigger(background: BackgroundTasks, campaign: str = "pao"):
    """Kick off an Apify scrape for the active roster of one campaign."""
    st = state_for(campaign)
    if st.get("status") == "running":
        raise HTTPException(status_code=409, detail="กำลังดึงข้อมูลอยู่แล้ว รอให้เสร็จก่อน")
    st.update(status="running", message="เริ่มงาน…", posts=0)
    background.add_task(refresh_report, campaign)
    return {"status": "started", "campaign": campaign}


@router.get("/report/refresh/status")
def report_refresh_status(campaign: str = "pao"):
    return state_for(campaign)


@router.post("/report/profiles")
def report_profiles_trigger(background: BackgroundTasks, campaign: str = "sahagroup"):
    """Fetch profile pictures (+followers) for the campaign roster — no post
    links needed. Scrapes TikTok profiles in the background."""
    st = state_for("pf:" + campaign)
    if st.get("status") == "running":
        raise HTTPException(status_code=409, detail="กำลังดึงรูปโปรไฟล์อยู่แล้ว")
    st.update(status="running", message="เริ่มงาน…", posts=0)
    background.add_task(fetch_profiles, campaign)
    return {"status": "started", "campaign": campaign}


@router.get("/report/profiles/status")
def report_profiles_status(campaign: str = "sahagroup"):
    return state_for("pf:" + campaign)


# ----------------------------------------------------------------------------
# Apify token management (open, no auth) — view masked + edit
# ----------------------------------------------------------------------------

class TokenIn(BaseModel):
    token: str


@router.get("/token")
def token_get():
    from app.settings import apify_token_source, get_apify_token, mask_token

    tok = get_apify_token()
    return {"masked": mask_token(tok), "source": apify_token_source(), "is_set": bool(tok)}


@router.post("/token")
def token_set(body: TokenIn):
    from app.settings import APIFY_TOKEN_KEY, mask_token, set_setting

    tok = (body.token or "").strip()
    if len(tok) < 10:
        raise HTTPException(400, "Token สั้นเกินไป ดูเหมือนไม่ถูกต้อง")
    set_setting(APIFY_TOKEN_KEY, tok)
    return {"status": "saved", "masked": mask_token(tok), "source": "database"}


# ----------------------------------------------------------------------------
# Campaign metadata CRUD — powers the home page (list) and "+ Create Campaign"
# ----------------------------------------------------------------------------


def _campaign_dict(c: Campaign, roster_count: int = 0, refreshed_at=None) -> dict:
    return {
        "key": c.key,
        "name": c.name,
        "emoji": c.emoji or "📊",
        "subtitle": c.subtitle or "",
        "groups": json.loads(c.groups_json) if c.groups_json else [],
        "subgroups": json.loads(c.subgroups_json) if c.subgroups_json else [],
        "active": c.active,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "roster_count": roster_count,
        "refreshed_at": refreshed_at.isoformat() if refreshed_at else None,
    }


class CampaignIn(BaseModel):
    key: Optional[str] = None
    name: str
    emoji: Optional[str] = "📊"
    subtitle: Optional[str] = ""
    groups: Optional[list[str]] = None
    subgroups: Optional[list[str]] = None


class CampaignPatch(BaseModel):
    name: Optional[str] = None
    emoji: Optional[str] = None
    subtitle: Optional[str] = None
    groups: Optional[list[str]] = None
    subgroups: Optional[list[str]] = None
    active: Optional[bool] = None


@router.get("/campaigns")
def list_campaigns(limit: int = Query(15, ge=1, le=100),
                   include_inactive: bool = Query(False),
                   session: Session = Depends(db_dependency)):
    """Latest N campaigns (default 15) — home page grid. Attaches roster_count
    and refreshed_at (max ReportPost.scraped_at) so cards can show status."""
    q = select(Campaign)
    if not include_inactive:
        q = q.where(Campaign.active.is_(True))
    q = q.order_by(Campaign.created_at.desc()).limit(limit)
    rows = session.scalars(q).all()

    counts = dict(
        session.execute(
            select(ReportKol.campaign, func.count()).where(
                ReportKol.active.is_(True)
            ).group_by(ReportKol.campaign)
        ).all()
    )
    last = dict(
        session.execute(
            select(ReportPost.campaign, func.max(ReportPost.scraped_at)).group_by(ReportPost.campaign)
        ).all()
    )
    out = []
    for c in rows:
        d = _campaign_dict(c, counts.get(c.key, 0), last.get(c.key))
        # creator shown on Home cards — this endpoint is auth-protected, the
        # open single-campaign GET (used by client view pages) omits it
        d["created_by"] = c.created_by
        d["created_by_photo"] = c.created_by_photo
        out.append(d)
    return {"campaigns": out}


@router.get("/campaigns/{key}")
def get_campaign(key: str, session: Session = Depends(db_dependency)):
    c = session.get(Campaign, key)
    if not c:
        raise HTTPException(404, f"ไม่พบแคมเปญ '{key}'")
    roster_count = session.scalar(
        select(func.count()).select_from(ReportKol).where(
            ReportKol.campaign == key, ReportKol.active.is_(True))
    ) or 0
    last = session.scalar(
        select(func.max(ReportPost.scraped_at)).where(ReportPost.campaign == key)
    )
    return _campaign_dict(c, roster_count, last)


def _next_campaign_key(session: Session) -> str:
    """Auto-generate the next sequential campaign code: 00001, 00002, …

    Based on the max existing numeric key across ALL campaigns (incl. archived),
    so codes never repeat even after a campaign is deleted. Legacy string keys
    (sahagroup/pao/…) are ignored for numbering."""
    nums = [int(k) for (k,) in session.query(Campaign.key).all() if k.isdigit()]
    n = (max(nums) + 1) if nums else 1
    key = f"{n:05d}"
    while session.get(Campaign, key):  # safety against a collision
        n += 1
        key = f"{n:05d}"
    return key


def _slug_from_name(name: str) -> str:
    """Friendly URL key from the campaign name: 'Bon (2026-061) DNA High
    Protein' -> 'bon-2026-061-dna-high-protein'. Thai-only names produce an
    empty slug (keys allow a-z/0-9/- only) — callers fall back to a number."""
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower())
    return re.sub(r"-+", "-", s).strip("-")[:32].strip("-")


def _campaign_key_for(session: Session, name: str) -> str:
    base = _slug_from_name(name)
    if not base or base.isdigit():  # unusable slug -> running code
        return _next_campaign_key(session)
    key = base
    n = 2
    while session.get(Campaign, key):  # name collision -> -2, -3, ...
        suffix = f"-{n}"
        key = base[: 32 - len(suffix)] + suffix
        n += 1
    return key


def _thumb_datauri(b64: str, ftype) -> Optional[str]:
    """Downscale a base64 employee photo to a tiny 64px JPEG data URI so the
    campaign list stays light."""
    try:
        import base64 as _b64
        import io as _io

        from PIL import Image
        im = Image.open(_io.BytesIO(_b64.b64decode(b64))).convert("RGB")
        im.thumbnail((64, 64))
        out = _io.BytesIO()
        im.save(out, "JPEG", quality=80)
        return "data:image/jpeg;base64," + _b64.b64encode(out.getvalue()).decode()
    except Exception:  # noqa: BLE001
        return None


def _creator_info(authorization: Optional[str]) -> tuple:
    """(full name, tiny photo) of the signed-in creator, from their Wazzup
    profile. Best-effort — campaign creation never fails because of this."""
    try:
        token = ""
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        if not token:
            return None, None
        from app.auth import wazzup_profile
        pd = wazzup_profile(token) or {}
        p = pd.get("profile") or {}
        name = p.get("empThaiName") or p.get("empEngName")
        photo = None
        if p.get("wazzupPhotoBase64"):
            photo = _thumb_datauri(p["wazzupPhotoBase64"], p.get("wazzupPhotoFileType"))
        if not photo and (p.get("profileURL") or "").startswith("http"):
            photo = p["profileURL"]
        return name, photo
    except Exception:  # noqa: BLE001
        return None, None


@router.post("/campaigns")
def create_campaign(body: CampaignIn, authorization: Optional[str] = Header(None),
                    session: Session = Depends(db_dependency)):
    """Create a new campaign. The URL key is a friendly slug generated from the
    campaign name (running code as fallback) — editable later via Edit."""
    if not (body.name or "").strip():
        raise HTTPException(400, "name ห้ามว่าง")
    import secrets as _secrets
    created_by, created_photo = _creator_info(authorization)
    key = _campaign_key_for(session, body.name)
    c = Campaign(
        key=key,
        view_token=_secrets.token_urlsafe(9),
        created_by=created_by,
        created_by_photo=created_photo,
        name=body.name.strip(),
        emoji=(body.emoji or "📊").strip()[:8],
        subtitle=(body.subtitle or "").strip() or None,
        groups_json=json.dumps(body.groups or [], ensure_ascii=False),
        subgroups_json=json.dumps(body.subgroups or [], ensure_ascii=False),
        active=True,
    )
    session.add(c)
    try:
        session.commit()
    except IntegrityError:  # two simultaneous creates raced to the same key
        session.rollback()
        raise HTTPException(409, "สร้างพร้อมกันหลายรายการ — ลองกดสร้างอีกครั้ง")
    session.refresh(c)
    return _campaign_dict(c, 0, None)


@router.patch("/campaigns/{key}")
def update_campaign(key: str, body: CampaignPatch, session: Session = Depends(db_dependency)):
    c = session.get(Campaign, key)
    if not c:
        raise HTTPException(404, f"ไม่พบแคมเปญ '{key}'")
    if body.name is not None:
        c.name = body.name.strip()
    if body.emoji is not None:
        c.emoji = body.emoji.strip()[:8] or "📊"
    if body.subtitle is not None:
        c.subtitle = body.subtitle.strip() or None
    if body.groups is not None:
        c.groups_json = json.dumps(body.groups, ensure_ascii=False)
    if body.subgroups is not None:
        c.subgroups_json = json.dumps(body.subgroups, ensure_ascii=False)
    if body.active is not None:
        c.active = body.active
    session.commit()
    session.refresh(c)
    return _campaign_dict(c)


@router.delete("/campaigns/{key}")
def delete_campaign(key: str, session: Session = Depends(db_dependency)):
    """Soft delete — set active=false so KOL data is preserved. Hidden from
    home page but data + URL still work."""
    c = session.get(Campaign, key)
    if not c:
        raise HTTPException(404, f"ไม่พบแคมเปญ '{key}'")
    c.active = False
    session.commit()
    return {"status": "archived", "key": key}


@router.get("/campaigns/{key}/view-token")
def campaign_view_token(key: str, session: Session = Depends(db_dependency)):
    """The campaign's client-link token (random, unguessable). Generated on
    first request. Auth-protected — never exposed on the open meta endpoint."""
    import secrets as _secrets
    c = session.get(Campaign, key)
    if not c:
        raise HTTPException(404, f"ไม่พบแคมเปญ '{key}'")
    if not c.view_token:
        c.view_token = _secrets.token_urlsafe(9)
        session.commit()
    return {"token": c.view_token}


class CampaignRename(BaseModel):
    new_key: str


@router.post("/campaigns/{key}/rename")
def rename_campaign(key: str, body: CampaignRename, session: Session = Depends(db_dependency)):
    """Change a campaign's URL key everywhere (campaigns, report_kols,
    report_posts, and its settings). The report URL becomes /c/<new_key>."""
    import re as _re
    from app.models import AppSetting
    c = session.get(Campaign, key)
    if not c:
        raise HTTPException(404, f"ไม่พบแคมเปญ '{key}'")
    nk = _re.sub(r"[^a-z0-9-]+", "-", (body.new_key or "").strip().lower()).strip("-")[:32]
    if not nk or len(nk) < 2:
        raise HTTPException(400, "รหัสต้องเป็น a-z 0-9 หรือ - เท่านั้น (2–32 ตัวอักษร)")
    if nk == key:
        return {"status": "unchanged", "key": key}
    if session.get(Campaign, nk):
        raise HTTPException(409, f"มีรหัส '{nk}' อยู่แล้ว")

    session.execute(update(Campaign).where(Campaign.key == key).values(key=nk))
    session.execute(update(ReportKol).where(ReportKol.campaign == key).values(campaign=nk))
    session.execute(update(ReportPost).where(ReportPost.campaign == key).values(campaign=nk))
    for pref in ("refresh_cost:", "sheet_url:"):
        old_row = session.get(AppSetting, pref + key)
        if old_row is not None:
            new_row = session.get(AppSetting, pref + nk)
            if new_row:
                new_row.value = old_row.value
            else:
                session.add(AppSetting(key=pref + nk, value=old_row.value))
            session.delete(old_row)
    try:
        session.commit()
    except IntegrityError:  # concurrent rename raced to the same key
        session.rollback()
        raise HTTPException(409, f"มีรหัส '{nk}' อยู่แล้ว")
    return {"status": "renamed", "key": nk}


# ----------------------------------------------------------------------------
# Image proxy + cache — TikTok avatar/cover URLs are signed and expire after a
# few days, so KOL pictures vanish once the link dies. We fetch each image once
# (while its URL is still valid) and serve our own copy from here forever.
# ----------------------------------------------------------------------------

@router.get("/img")
def img_proxy(u: str = Query(...), session: Session = Depends(db_dependency)):
    if not is_public_http_url(u):  # SSRF guard: no internal/metadata addresses
        raise HTTPException(400, "bad url")
    h = hashlib.sha256(u.encode("utf-8")).hexdigest()[:40]
    cache_headers = {"Cache-Control": "public, max-age=604800"}

    row = session.get(ImageCache, h)
    if row and row.data:
        return Response(content=row.data, media_type=row.content_type or "image/jpeg",
                        headers=cache_headers)

    # Not cached yet — fetch server-side with a Referer matching the CDN's own
    # site (a foreign referer can 403), retrying bare; store bytes and serve.
    # Best-effort: on failure fall back to a redirect (never worse than direct).
    from app.pptx_report import _UA, _referer_for
    import httpx as _httpx
    for ref in (_referer_for(u), None):
        try:
            headers = {"User-Agent": _UA,
                       "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"}
            if ref:
                headers["Referer"] = ref
            r = _httpx.get(u, timeout=15, follow_redirects=True, headers=headers)
            ct = (r.headers.get("content-type") or "image/jpeg").split(";")[0].strip()
            if r.status_code == 200 and r.content and ct.startswith("image/"):
                try:
                    session.merge(ImageCache(hash=h, content_type=ct, data=r.content))
                    session.commit()
                except Exception:  # noqa: BLE001 — caching is best-effort
                    session.rollback()
                return Response(content=r.content, media_type=ct, headers=cache_headers)
        except Exception:  # noqa: BLE001
            continue
    return RedirectResponse(u, status_code=302)


@router.post("/token/test")
def token_test():
    """Validate the current token against Apify (cheap user endpoint)."""
    import httpx as _httpx

    from app.settings import get_apify_token

    tok = get_apify_token()
    if not tok:
        raise HTTPException(400, "ยังไม่มี token")
    try:
        r = _httpx.get("https://api.apify.com/v2/users/me", params={"token": tok}, timeout=20)
        if r.status_code == 200:
            data = r.json().get("data", {})
            return {"ok": True, "username": data.get("username"), "plan": (data.get("plan") or {}).get("id")}
        return {"ok": False, "status": r.status_code, "detail": "token ใช้ไม่ได้ (อาจหมดอายุ)"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": str(exc)[:120]}
