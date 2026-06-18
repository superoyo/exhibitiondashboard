"""REST API routers (brief section 10). All endpoints return JSON."""
from __future__ import annotations

import datetime as dt
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config, queries
from app.db import db_dependency
from app.models import Kol, ReportKol
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


class KolPatch(BaseModel):
    display: Optional[str] = None
    group: Optional[str] = None
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
    return out


def _roster_endpoints(model, with_url: bool):
    """Build a list/add/update/delete handler set bound to one ORM model."""

    def list_all(session: Session = Depends(db_dependency)):
        rows = session.scalars(select(model).order_by(model.content_group, model.username)).all()
        return {"kols": [_serialize(k) for k in rows]}

    def add(body: KolIn, session: Session = Depends(db_dependency)):
        username = (body.username or "").strip().lstrip("@")
        if not username:
            raise HTTPException(400, "username ห้ามว่าง")
        if session.scalar(select(model).where(model.username == username)):
            raise HTTPException(409, f"มี @{username} อยู่แล้ว")
        k = model(
            username=username,
            display=(body.display or username).strip(),
            content_group=body.group.strip(),
            active=True,
        )
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
        if with_url and body.url is not None:
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


for _name, _model, _url in (("tracker", Kol, False), ("report", ReportKol, True)):
    _list, _add, _update, _delete = _roster_endpoints(_model, _url)
    router.add_api_route(f"/roster/{_name}", _list, methods=["GET"])
    router.add_api_route(f"/roster/{_name}", _add, methods=["POST"])
    router.add_api_route(f"/roster/{_name}/{{item_id}}", _update, methods=["PATCH"])
    router.add_api_route(f"/roster/{_name}/{{item_id}}", _delete, methods=["DELETE"])
