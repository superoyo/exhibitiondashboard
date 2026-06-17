"""REST API routers (brief section 10). All endpoints return JSON."""
from __future__ import annotations

import datetime as dt
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app import config, queries
from app.db import db_dependency
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
