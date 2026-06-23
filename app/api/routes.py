"""REST API routers (brief section 10). All endpoints return JSON."""
from __future__ import annotations

import datetime as dt
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config, queries
from app.db import db_dependency
from app.models import Kol, ReportKol, ReportPost
from app.report_refresh import fetch_profiles, refresh_report, state_for
from app.scrape import run_daily_scrape

log = logging.getLogger("api")
router = APIRouter(prefix="/api")


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
        rows = session.scalars(q.order_by(model.content_group, model.username)).all()
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
            if body.subgroup is not None:
                k.subgroup = body.subgroup.strip() or None
            if body.url:
                k.url = body.url.strip()
        session.add(k)
        session.commit()
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
        if is_report and body.url is not None:
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
        .order_by(ReportKol.content_group, ReportKol.subgroup)
    ).all()
    posts_by_user: dict = {}
    for p in session.scalars(select(ReportPost).where(ReportPost.campaign == campaign)).all():
        u = p.username.lower()
        if u not in posts_by_user or p.views > posts_by_user[u].views:
            posts_by_user[u] = p

    records = []
    scraped = 0
    for k in roster:
        p = posts_by_user.get(k.username.lower())
        if p:
            scraped += 1
        records.append({
            "username": k.username,
            "nickname": k.display,
            "category": k.subgroup or k.content_group,
            "biggroup": k.content_group,
            "followers": k.followers,
            "views": p.views if p else 0,
            "likes": p.likes if p else 0,
            "comments": p.comments if p else 0,
            "shares": p.shares if p else 0,
            "saves": p.saves if p else 0,
            "posted": (p.posted_at.date().isoformat() if p and p.posted_at else ""),
            "url": k.url or (p.url if p else "") or "",
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
        "roster_count": len(roster),
        "post_count": scraped,
        "cost_total": cost["total"],
        "cost_count": cost["count"],
    }


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
