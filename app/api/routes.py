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
    is_profile_link,
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
    # Commercial fields (report roster only). Numbers sent as -1 CLEAR the
    # value; `kpis` replaces the whole list ([] clears). Absent means "leave
    # alone", so saving a name never wipes a price.
    cost_thb: Optional[float] = None
    boost_thb: Optional[float] = None
    kpis: Optional[list[dict]] = None  # [{metric, target}]


def _clean_kpis(raw: Optional[list]) -> Optional[str]:
    """[{metric, target}] -> kpi_json, dropping junk. None when nothing valid.

    Metric is free text (lowercased, capped) — a new sales unit must be data,
    not a 422 — but a KPI without a positive numeric target is meaningless and
    is dropped rather than stored as noise.
    """
    out = []
    for item in raw or []:
        try:
            target = int(float(item.get("target") or 0))
        except (TypeError, ValueError):
            continue
        if target <= 0:
            continue
        out.append({"metric": str(item.get("metric") or "").strip().lower()[:16],
                    "target": target})
    return json.dumps(out, ensure_ascii=False) if out else None


def _kpis_of(k) -> list:
    try:
        return json.loads(k.kpi_json) if k.kpi_json else []
    except Exception:  # noqa: BLE001
        return []


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
    # Commercial fields, report roster only. Safe HERE because every
    # /api/roster/* route requires login; the open report endpoints build their
    # own payloads and never touch these.
    if hasattr(k, "cost_thb"):
        out["cost_thb"] = float(k.cost_thb) if k.cost_thb is not None else None
        out["boost_thb"] = float(k.boost_thb) if k.boost_thb is not None else None
        out["kpis"] = _kpis_of(k)
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
        if is_report:
            # -1 (numbers) means CLEAR; absent means leave alone.
            if body.cost_thb is not None:
                k.cost_thb = None if body.cost_thb < 0 else round(body.cost_thb, 2)
            if body.boost_thb is not None:
                k.boost_thb = None if body.boost_thb < 0 else round(body.boost_thb, 2)
            if body.kpis is not None:  # full replacement; [] clears
                k.kpi_json = _clean_kpis(body.kpis)
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
    # From the planner's sheet — see the 0019/0020 migration docstrings.
    cost_thb: Optional[float] = None
    boost_thb: Optional[float] = None
    kpis: Optional[list[dict]] = None  # [{metric, target}]


class BulkGroupKpiIn(BaseModel):
    group: str
    kpis: list[dict]


class BulkRosterIn(BaseModel):
    kols: list[BulkKolIn]
    # Group-total KPIs the parser found as vertically-merged cells. Upserted,
    # not replace-all: a re-upload of a file WITHOUT merged KPI cells must not
    # wipe targets the team keyed in by hand on the group-KPI card.
    group_kpis: Optional[list[BulkGroupKpiIn]] = None
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
        if not u:
            continue
        if u in seen:
            # same account listed on several rows (a page posting more than
            # once) — merge the links; the first row keeps name/group/order
            prev = seen[u]
            prev.links = (prev.links or []) + (k.links or [])
            if not prev.followers and k.followers:
                prev.followers = k.followers
            # commercial fields: first row wins, later rows only fill gaps
            for f in ("cost_thb", "boost_thb", "kpis"):
                if not getattr(prev, f) and getattr(k, f):
                    setattr(prev, f, getattr(k, f))
        else:
            seen[u] = k
    if not seen:
        raise HTTPException(400, "ไม่พบรายชื่อ KOL ที่ใช้ได้ในไฟล์/ชีต")

    session.execute(delete(ReportKol).where(ReportKol.campaign == campaign))
    for i, (u, k) in enumerate(seen.items()):
        links, dedup = [], set()
        for ln in (k.links or []):
            if not (ln.url and ln.url.strip()):
                continue
            url = ln.url.strip()
            key = ((ln.platform or ""), url.split("?")[0].rstrip("/").lower())
            if key in dedup:
                continue
            dedup.add(key)
            links.append({"platform": (ln.platform or ""), "url": url,
                          "handle": (ln.handle or "")})
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
            cost_thb=round(k.cost_thb, 2) if k.cost_thb and k.cost_thb > 0 else None,
            boost_thb=round(k.boost_thb, 2) if k.boost_thb and k.boost_thb > 0 else None,
            kpi_json=_clean_kpis(k.kpis),
            active=True,
        ))
    # Group-total KPIs from merged cells — upsert per group.
    if body.group_kpis:
        from app.models import ReportGroupKpi
        for g in body.group_kpis:
            name = (g.group or "").strip()
            cleaned = _clean_kpis(g.kpis)
            if not name or not cleaned:
                continue
            row = session.scalar(select(ReportGroupKpi).where(
                ReportGroupKpi.campaign == campaign,
                ReportGroupKpi.group_name == name))
            if row:
                row.kpi_json = cleaned
            else:
                session.add(ReportGroupKpi(campaign=campaign, group_name=name,
                                           kpi_json=cleaned))
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


# ---- Group-level KPIs -------------------------------------------------------
# A package group is sold on a TOTAL ("7M Impressions across Micro Package"),
# which belongs to no roster row. Entered on the web per group — the planner
# sheets write it as merged/summary cells that row-wise parsing cannot own.
# Authenticated like every /api/roster/* route.

class GroupKpiIn(BaseModel):
    group: str
    kpis: list[dict]  # [{metric, target}] — [] deletes the group's entry


@router.get("/roster/report/groupkpi")
def group_kpis_get(campaign: str = "pao", session: Session = Depends(db_dependency)):
    """{group_name: [{metric, target}]} for one campaign."""
    from app.models import ReportGroupKpi
    out = {}
    for row in session.scalars(select(ReportGroupKpi).where(
            ReportGroupKpi.campaign == campaign)).all():
        try:
            out[row.group_name] = json.loads(row.kpi_json)
        except Exception:  # noqa: BLE001
            out[row.group_name] = []
    return {"groups": out}


@router.post("/roster/report/groupkpi")
def group_kpis_set(body: GroupKpiIn, campaign: str = "pao",
                   session: Session = Depends(db_dependency)):
    """Upsert one group's KPI list; an empty list removes the row."""
    from app.models import ReportGroupKpi
    group = (body.group or "").strip()
    if not group:
        raise HTTPException(400, "ต้องระบุชื่อกลุ่ม")
    row = session.scalar(select(ReportGroupKpi).where(
        ReportGroupKpi.campaign == campaign,
        ReportGroupKpi.group_name == group))
    cleaned = _clean_kpis(body.kpis)
    if not cleaned:
        if row:
            session.delete(row)
            session.commit()
        return {"status": "cleared", "group": group}
    if row:
        row.kpi_json = cleaned
    else:
        session.add(ReportGroupKpi(campaign=campaign, group_name=group,
                                   kpi_json=cleaned))
    session.commit()
    return {"status": "saved", "group": group, "kpis": json.loads(cleaned)}


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
# FB/IG embed the post's canonical URL in og:url even when the share short
# link itself doesn't redirect (interstitial page)
_RE_OGURL = re.compile(r'property="og:url"\s+content="([^"]+)"', re.I)
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
                    if not h:
                        m = _RE_OGURL.search(r.text or "")
                        og = m.group(1) if m else ""
                        if og and "login" not in og.lower():
                            h = _handle_from_url(og)
                            if h:
                                final = og
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
        # The KOL's profile page per platform, when the planner's file supplied
        # one — clicking a name should land on the channel, not nowhere. Rows
        # without one simply aren't links (the team's call: ไม่ใส่ก็ช่างมัน).
        profile_by_plat = {ln["platform"]: ln["url"] for ln in links
                           if ln.get("url") and is_profile_link(ln["platform"], ln["url"])}
        # Rows are driven by WORK links only. A profile link is identity, not a
        # post: giving it a row of its own next to the post's row would double
        # every stat, and putting it in `url` would flip the influencer view's
        # Active/Waiting split. Profile-only KOLs still get a per-platform row
        # (correct badge, zero stats) with the profile reachable via profile_url.
        links = [ln for ln in links
                 if not (ln.get("url") and is_profile_link(ln["platform"], ln["url"]))]
        if not links and profile_by_plat:
            links = [{"platform": plat, "url": "", "handle": k.username.lower()}
                     for plat in profile_by_plat]
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
                "profile_url": profile_by_plat.get(plat, ""),
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
        # per-button split; anything spent before the split existed shows up as
        # total minus the sum of these
        "cost_by_kind": cost["by_kind"],
    }


@router.post("/report/tiein")
def report_tiein_trigger(background: BackgroundTasks, campaign: str = "pao"):
    """AI tie-in shots: download the campaign's TikTok videos, let Claude pick
    the frame showing the product, use it as the PPTX post preview."""
    from app.tiein import run_tiein
    st = state_for("ti:" + campaign)
    if st.get("status") == "running":
        raise HTTPException(status_code=409, detail="กำลังหา tie-in shot อยู่แล้ว")
    st.update(status="running", message="เริ่มงาน…", posts=0)
    background.add_task(run_tiein, campaign)
    return {"status": "started", "campaign": campaign}


@router.get("/report/tiein/status")
def report_tiein_status(campaign: str = "pao"):
    return state_for("ti:" + campaign)


@router.get("/jobs/active")
def jobs_active():
    """Every background job running now, plus ones that just ended.

    Feeds the status dock, which sits in the page frame and so appears on every
    internal page — a job's progress used to be visible only on the page that
    started it."""
    from app.jobs import active_jobs
    return active_jobs()


@router.get("/report/comments")
def report_comments(campaign: str = "pao"):
    """Comment breakdown for the campaign panel: the topic split, how many
    comments touch the product, and the top themes. Reads stored rows only —
    never scrapes, so opening the report costs nothing."""
    from app.comments import summary
    return summary(campaign)


@router.get("/report/comments/list")
def report_comments_list(campaign: str = "pao", category: str = "",
                         offset: int = 0, limit: int = 20):
    """One page of product-related comments, optionally narrowed to one topic.

    Paged and filtered on the server: a campaign's product comments run into the
    thousands, and the panel only ever shows twenty at a time."""
    from app.comments import list_comments
    return list_comments(campaign, category or None, max(0, offset), limit)


@router.get("/report/comments/export")
def report_comments_export(campaign: str = "pao"):
    """Every stored comment, flat, for the Excel export.

    Returns JSON and lets the browser build the .xlsx: the frontend already
    bundles SheetJS for roster import, so this needs no new server dependency
    and no temp files, and Thai text avoids the CSV encoding traps entirely.
    Unfiltered on purpose — the panel filters because it shows twenty at a time,
    whereas a spreadsheet is where someone goes to see everything."""
    from app.comments import export_rows
    return export_rows(campaign)


@router.post("/report/comments/refresh")
def report_comments_trigger(background: BackgroundTasks, campaign: str = "pao"):
    """Scrape + classify this campaign's comments.

    Deliberately its own endpoint (and its own button) rather than part of
    Refresh Data: comments are billed per comment by Apify, so this is the most
    expensive action in the product and must never fire as a side effect of
    someone updating stats."""
    from app.comments import run_comment_refresh
    st = state_for("cm:" + campaign)
    if st.get("status") == "running":
        raise HTTPException(status_code=409, detail="กำลังดึงคอมเมนต์อยู่แล้ว")
    st.update(status="running", message="เริ่มงาน…", posts=0)
    background.add_task(run_comment_refresh, campaign)
    return {"status": "started", "campaign": campaign}


@router.get("/report/comments/status")
def report_comments_status(campaign: str = "pao"):
    return state_for("cm:" + campaign)


# ---------------------------------------------------------------------------
# Client-facing comment reads, addressed by view token (open, no session)
# ---------------------------------------------------------------------------

def _view_campaign(view_token: str) -> str:
    """The campaign a client link points at, or 404.

    The token IS the credential: `secrets.token_urlsafe(9)` — 72 bits, the same
    unguessable string the /v/ page itself is protected by. Anyone holding it
    already has the report.

    This is why these endpoints take a token in the PATH instead of the
    `?campaign=` the authenticated ones use. Campaign keys are short guessable
    strings ('pao', '00008'), so opening a comment endpoint keyed on them would
    hand every client's comments — with the commenters' names — to anyone who
    tried a few. That is exactly how /api/campaigns/summary came to serve the
    whole client roster.
    """
    # Function-level import: app.main imports this module to mount the router.
    from app.main import _campaign_for_view_token

    key = _campaign_for_view_token((view_token or "").strip())
    if not key:
        raise HTTPException(status_code=404, detail="ไม่พบลิงก์รายงานนี้")
    return key


@router.get("/view/{view_token}/comments")
def view_comments(view_token: str):
    """Comment breakdown for a client link. Same rollup the internal panel reads."""
    from app.comments import summary
    return summary(_view_campaign(view_token))


@router.get("/view/{view_token}/comments/list")
def view_comments_list(view_token: str, category: str = "", offset: int = 0,
                       limit: int = 20):
    """One page of product-related comments for a client link."""
    from app.comments import list_comments
    return list_comments(_view_campaign(view_token), category or None,
                         max(0, offset), limit)


@router.get("/view/{view_token}/commercial")
def view_commercial(view_token: str, session: Session = Depends(db_dependency)):
    """Per-KOL sold KPI / price / boost + group KPIs, for a client link.

    These figures used to be login-only everywhere. On 2026-09-01 the team
    decided the client link shows the full commercial picture — the client
    bought these numbers. They stay OFF /api/report/data on purpose: that
    endpoint is keyed by short guessable campaign keys, while this one needs
    the 72-bit token, i.e. the link itself.
    """
    campaign = _view_campaign(view_token)
    kols = {}
    for k in session.scalars(select(ReportKol).where(
            ReportKol.campaign == campaign, ReportKol.active.is_(True))).all():
        kpis = _kpis_of(k)
        if k.cost_thb is None and k.boost_thb is None and not kpis:
            continue
        kols[k.username.lower()] = {
            "cost_thb": float(k.cost_thb) if k.cost_thb is not None else None,
            "boost_thb": float(k.boost_thb) if k.boost_thb is not None else None,
            "kpis": kpis,
        }
    from app.models import ReportGroupKpi
    groups = {}
    for row in session.scalars(select(ReportGroupKpi).where(
            ReportGroupKpi.campaign == campaign)).all():
        try:
            groups[row.group_name] = json.loads(row.kpi_json)
        except Exception:  # noqa: BLE001
            groups[row.group_name] = []
    return {"kols": kols, "group_kpis": groups}


@router.get("/view/{view_token}/advisor")
def view_advisor(view_token: str):
    """The stored Performance Analysis for a client link — read-only; running
    a new analysis stays a logged-in button. The v2 output is grades and
    engagement figures only (money is banned from it by the prompt)."""
    from app.advisor import stored
    return stored(_view_campaign(view_token))


# ---- Performance advisor (running it stays internal) ----

@router.get("/report/advisor")
def report_advisor(campaign: str = "pao"):
    """The stored analysis with its timestamp — reading costs nothing."""
    from app.advisor import stored
    return stored(campaign)


@router.post("/report/advisor/run")
def report_advisor_run(background: BackgroundTasks, campaign: str = "pao"):
    """Run the analyst over the campaign's current numbers (one Claude call).

    Its own explicit press: boost advice goes stale in days, and re-billing AI
    silently on every page open would hide when the advice was generated."""
    from app.advisor import run_advisor
    st = state_for("adv:" + campaign)
    if st.get("status") == "running":
        raise HTTPException(status_code=409, detail="กำลังวิเคราะห์อยู่แล้ว")
    st.update(status="running", message="เริ่มงาน…", posts=0)
    background.add_task(run_advisor, campaign)
    return {"status": "started", "campaign": campaign}


@router.get("/report/advisor/status")
def report_advisor_status(campaign: str = "pao"):
    return state_for("adv:" + campaign)


@router.get("/ai/status")
def ai_status_route(force: bool = False):
    """Is the Claude AI key set + funded? Shown on the settings page so the
    team sees 'เครดิตหมด' in the UI instead of digging through job errors."""
    from app.tiein import ai_status
    return ai_status(force)


@router.get("/kol-directory")
def kol_directory(session: Session = Depends(db_dependency)):
    """Master directory: every KOL ever used in ANY campaign, with per-campaign
    aggregated stats — the team's record of who worked on what and how it did."""
    camps = {c.key: {"name": c.name, "emoji": c.emoji or "📊"}
             for c in session.scalars(select(Campaign)).all()}
    posts_by: dict = {}
    for p in session.scalars(select(ReportPost)).all():
        posts_by.setdefault((p.campaign, (p.username or "").lower()), []).append(p)
    out: dict = {}
    for k in session.scalars(select(ReportKol)).all():
        u = (k.username or "").strip().lower()
        if not u:
            continue
        d = out.setdefault(u, {
            "username": u, "display": None, "avatar": None, "followers": 0,
            "campaigns": [], "views": 0, "likes": 0, "comments": 0,
            "shares": 0, "saves": 0, "posts": 0, "platforms": set(),
            "last_posted": None,
        })
        if k.display and k.display != k.username and not d["display"]:
            d["display"] = k.display
        if k.avatar_url and not d["avatar"]:
            d["avatar"] = k.avatar_url
        if (k.followers or 0) > d["followers"]:
            d["followers"] = k.followers or 0
        cm = camps.get(k.campaign) or {"name": k.campaign, "emoji": "📊"}
        c = {"key": k.campaign, "name": cm["name"], "emoji": cm["emoji"],
             "category": k.content_group, "posts": 0, "views": 0, "likes": 0,
             "comments": 0, "shares": 0, "saves": 0, "platforms": [],
             "last_posted": None}
        plats = set()
        for p in posts_by.get((k.campaign, u), []):
            c["posts"] += 1
            for f in ("views", "likes", "comments", "shares", "saves"):
                c[f] += getattr(p, f) or 0
            if p.platform:
                plats.add(p.platform)
            if p.posted_at:
                iso = p.posted_at.isoformat()
                if not c["last_posted"] or iso > c["last_posted"]:
                    c["last_posted"] = iso
        c["platforms"] = sorted(plats)
        d["campaigns"].append(c)
        d["posts"] += c["posts"]
        for f in ("views", "likes", "comments", "shares", "saves"):
            d[f] += c[f]
        d["platforms"].update(plats)
        if c["last_posted"] and (not d["last_posted"] or c["last_posted"] > d["last_posted"]):
            d["last_posted"] = c["last_posted"]
    kols = []
    for d in out.values():
        d["platforms"] = sorted(d["platforms"])
        d["display"] = d["display"] or d["username"]
        d["campaign_count"] = len(d["campaigns"])
        d["campaigns"].sort(key=lambda c: c["last_posted"] or "", reverse=True)
        kols.append(d)
    kols.sort(key=lambda d: (-d["campaign_count"], -d["views"]))
    return {"kols": kols, "total": len(kols)}


class PackshotIn(BaseModel):
    image_base64: str


@router.get("/report/packshot")
def packshot_get(campaign: str = "pao"):
    """Is a product pack shot uploaded for this campaign? (+ tiny preview)"""
    import base64 as _b64

    from app.tiein import _shrink, get_packshot
    img = get_packshot(campaign)
    if not img:
        return {"is_set": False}
    return {"is_set": True,
            "preview": "data:image/jpeg;base64,"
                       + _b64.b64encode(_shrink(img, 240)).decode()}


@router.post("/report/packshot")
def packshot_set(body: PackshotIn, campaign: str = "pao"):
    """Store the campaign's product pack shot — the tie-in AI uses it as the
    reference image when picking frames, which beats any text description."""
    import base64 as _b64

    from app.tiein import _shrink, packshot_hash
    try:
        raw = _b64.b64decode((body.image_base64 or "").split(",")[-1])
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "ไฟล์ภาพไม่ถูกต้อง")
    if not raw:
        raise HTTPException(400, "ไฟล์ภาพว่างเปล่า")
    if len(raw) > 8_000_000:
        raise HTTPException(400, "ไฟล์ใหญ่เกิน 8MB — ย่อรูปก่อนอัพโหลด")
    img = _shrink(raw, 1024)  # normalise to jpeg ≤1024px
    from app.db import session_scope
    with session_scope() as s:
        s.merge(ImageCache(hash=packshot_hash(campaign),
                           content_type="image/jpeg", data=img))
        # clips previously marked 'no product found' (marker = hash without an
        # image row) get another chance now that a reference image exists;
        # clips that already HAVE a shot are left alone
        retried = 0
        for p in s.scalars(select(ReportPost).where(
                ReportPost.campaign == campaign,
                ReportPost.tiein_hash.isnot(None))).all():
            if not s.get(ImageCache, p.tiein_hash):
                p.tiein_hash = None
                retried += 1
    # product description must be re-inferred WITH the new pack shot
    from app.settings import set_setting
    set_setting(f"product:{campaign}", "")
    return {"status": "saved", "unlocked": retried}


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


@router.get("/ai/key")
def ai_key_get():
    from app.settings import anthropic_key_source, get_anthropic_key, mask_token
    key = get_anthropic_key()
    return {"masked": mask_token(key), "source": anthropic_key_source(),
            "is_set": bool(key)}


@router.post("/ai/key")
def ai_key_set(body: TokenIn):
    """Save the Claude API key from the web UI (same pattern as the Apify
    token) — no Railway access needed. Verified live before saving."""
    from app.settings import ANTHROPIC_KEY_KEY, mask_token, set_setting
    key = (body.token or "").strip()
    if not key.startswith("sk-ant-") or len(key) < 20:
        raise HTTPException(400, "รูปแบบ key ไม่ถูกต้อง — ต้องขึ้นต้นด้วย sk-ant-")
    set_setting(ANTHROPIC_KEY_KEY, key)
    from app.tiein import ai_status
    status = ai_status(force=True)  # live-check the new key immediately
    return {"status": "saved", "masked": mask_token(key), "source": "database",
            "check": status}


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


@router.get("/campaigns/summary")
def campaigns_summary(keys: str = Query("", description="รหัสแคมเปญคั่นด้วยคอมมา ว่าง = ทุกแคมเปญ"),
                      days: int = Query(0, ge=0, le=730, description="นับเฉพาะโพสต์ที่ลงใน N วันล่าสุด (0 = ทั้งหมด)"),
                      session: Session = Depends(db_dependency)):
    """สรุปตัวเลขต่อแคมเปญแบบเบา สำหรับระบบภายนอกเอาไปทำตาราง (Agency Intelligence)

    ไม่ต้องดึง /report/data ทั้งก้อนมานับเอง และรวมแคมเปญที่ archive แล้วด้วย
    ถ้าระบุ keys มา

    total_views นับแบบเดียวกับหน้ารายงาน: เอาโพสต์ที่ยอดวิวสูงสุดของแต่ละ
    (username, platform) แล้วรวม — ไม่ใช่รวมทุกโพสต์ ไม่งั้นตัวเลขจะเกินจริง

    days = กรองเฉพาะโพสต์ที่ "ลงในช่วง N วันล่าสุด" (ดูจาก posted_at)
    ย้ำว่าไม่ใช่ "ยอดวิวที่เพิ่มขึ้นในช่วงนั้น" — ตาราง report_posts เก็บยอดล่าสุด
    ของแต่ละโพสต์เป็น snapshot ไม่ได้เก็บยอดรายวัน จึงคิดส่วนต่างรายวันไม่ได้
    โพสต์ที่ไม่มี posted_at จะไม่ถูกนับเมื่อระบุ days (ไม่รู้ว่าลงเมื่อไร)
    """
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days) if days else None
    wanted = [k.strip() for k in keys.split(",") if k.strip()]

    q = select(Campaign)
    if wanted:
        q = q.where(Campaign.key.in_(wanted))
    campaigns = session.scalars(q).all()

    kol_counts = dict(
        session.execute(
            select(ReportKol.campaign, func.count())
            .where(ReportKol.active.is_(True))
            .group_by(ReportKol.campaign)
        ).all()
    )

    def in_window(q):
        return q.where(ReportPost.posted_at.is_not(None), ReportPost.posted_at >= since) if since else q

    # ชั้นใน: โพสต์ที่วิวสูงสุดต่อ (campaign, username, platform)
    best = (
        in_window(
            select(
                ReportPost.campaign.label("campaign"),
                func.max(ReportPost.views).label("views"),
            )
        )
        .group_by(ReportPost.campaign, ReportPost.username, ReportPost.platform)
        .subquery()
    )
    view_totals = dict(
        session.execute(
            select(best.c.campaign, func.coalesce(func.sum(best.c.views), 0)).group_by(best.c.campaign)
        ).all()
    )
    post_counts = dict(
        session.execute(
            in_window(select(ReportPost.campaign, func.count())).group_by(ReportPost.campaign)
        ).all()
    )
    # KOL ที่มีโพสต์ในช่วงนี้ (ต่างจาก kol_count ที่นับทั้ง roster)
    active_kols = dict(
        session.execute(
            in_window(
                select(ReportPost.campaign, func.count(func.distinct(ReportPost.username)))
            ).group_by(ReportPost.campaign)
        ).all()
    )
    last = dict(
        session.execute(
            select(ReportPost.campaign, func.max(ReportPost.scraped_at)).group_by(ReportPost.campaign)
        ).all()
    )

    out = []
    for c in campaigns:
        refreshed = last.get(c.key)
        out.append({
            "key": c.key,
            "name": c.name,
            "active": c.active,
            "kol_count": kol_counts.get(c.key, 0),
            "active_kol_count": active_kols.get(c.key, 0),
            "post_count": post_counts.get(c.key, 0),
            "total_views": int(view_totals.get(c.key, 0) or 0),
            "refreshed_at": refreshed.isoformat() if refreshed else None,
        })
    out.sort(key=lambda d: d["key"])
    return {"window_days": days or None, "campaigns": out}


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
