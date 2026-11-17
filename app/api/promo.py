"""Promotion Page Package — read-only quota overview (/api/promo/*).

Every route here needs a signed-in session: it is not on the open-path list in
app/main.py and must not be added to it — the payload names clients, brands and
who on the team runs which deal.

The team keeps working in their own sheets. A deal is registered once (name,
team, link to the sheet); "sync" downloads that sheet, counts it with
app/promo_sheet and stores the snapshot. Nothing is ever written back.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import _creator_info, _to_download_url
from app.db import db_dependency
from app.models import PromoCampaign
from app.netguard import is_public_http_url
from app.promo_sheet import parse_workbook, totals

log = logging.getLogger("promo")

router = APIRouter(prefix="/api/promo")

MAX_SHEET_BYTES = 15 * 1024 * 1024
_NOT_PUBLIC = ("ระบบเปิดไฟล์นี้ไม่ได้ — ต้องตั้งแชร์เป็น \"ทุกคนที่มีลิงก์ดูได้\" "
               "แล้วใช้ลิงก์จากปุ่ม Share (ลิงก์ที่ก๊อปจากแถบที่อยู่ของ SharePoint ใช้ไม่ได้)")


def fetch_sheet(url: str) -> bytes:
    """Download a shared spreadsheet as xlsx bytes. ValueError = a reason the
    team can act on (in Thai)."""
    dl = _to_download_url((url or "").strip())
    if not is_public_http_url(dl):  # SSRF guard
        raise ValueError("ลิงก์ไฟล์ไม่ถูกต้อง")
    try:
        r = httpx.get(dl, timeout=25, follow_redirects=True, headers={
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/125.0.0.0 Safari/537.36")})
    except Exception as exc:  # noqa: BLE001
        raise ValueError("ดึงไฟล์ไม่สำเร็จ — ลองกดอัปเดตอีกครั้ง") from exc
    ctype = (r.headers.get("content-type") or "").lower()
    if r.status_code != 200 or ("html" in ctype and b"<html" in r.content[:2048].lower()):
        raise ValueError(_NOT_PUBLIC)
    if len(r.content) > MAX_SHEET_BYTES:
        raise ValueError("ไฟล์ใหญ่เกินไป (เกิน 15MB)")
    return r.content


def _read(url: str) -> tuple[Optional[dict], Optional[str]]:
    """(snapshot, None) or (None, reason). Never raises — runs in worker threads."""
    try:
        return parse_workbook(fetch_sheet(url)), None
    except ValueError as exc:
        return None, str(exc)
    except Exception:  # noqa: BLE001
        log.exception("promo sync failed")
        return None, "อ่านไฟล์ไม่สำเร็จ — รูปแบบตารางอาจต่างจากที่ระบบรู้จัก"


def _apply(c: PromoCampaign, data: Optional[dict], error: Optional[str]) -> None:
    if data is not None:
        c.data_json = json.dumps(data, ensure_ascii=False)
        c.synced_at = dt.datetime.now(dt.timezone.utc)
        c.sync_error = None
    else:  # keep the last good snapshot; say why this attempt failed
        c.sync_error = error


def _data(c: PromoCampaign) -> dict:
    try:
        return json.loads(c.data_json) if c.data_json else {}
    except ValueError:
        return {}


def _summary(c: PromoCampaign, data: Optional[dict] = None) -> dict:
    data = _data(c) if data is None else data
    t = totals(data)
    return {
        "id": c.id,
        "name": c.name,
        "team": c.team or "",
        "sheet_url": c.sheet_url,
        "synced_at": c.synced_at.isoformat() if c.synced_at else None,
        "sync_error": c.sync_error,
        "created_by": c.created_by,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        **t,
        # "จบแล้ว": every bought post is used. A deal that never synced has
        # quota 0 and is NOT complete — it must stay visible until it reads.
        "complete": t["quota"] > 0 and t["used"] >= t["quota"],
        "packs": [{k: p.get(k) for k in ("page", "expiry", "quota", "used", "reserved", "free")}
                  for p in data.get("packs") or []],
    }


def _detail(c: PromoCampaign) -> dict:
    data = _data(c)
    return {**_summary(c, data), "packs": data.get("packs") or [],
            "warnings": data.get("warnings") or []}


def _get(session: Session, promo_id: int) -> PromoCampaign:
    c = session.get(PromoCampaign, promo_id)
    if not c or not c.active:
        raise HTTPException(404, "ไม่พบงานนี้")
    return c


def _clean_url(raw: Optional[str]) -> str:
    url = (raw or "").strip()
    if not url.lower().startswith(("http://", "https://")) or len(url) > 2000:
        raise HTTPException(400, "วางลิงก์ไฟล์เช็กโควต้า (ขึ้นต้นด้วย https://)")
    return url


class PromoIn(BaseModel):
    name: str
    team: Optional[str] = ""
    sheet_url: str


class PromoPatch(BaseModel):
    name: Optional[str] = None
    team: Optional[str] = None
    sheet_url: Optional[str] = None


class SyncAllIn(BaseModel):
    # only re-read deals whose snapshot is older than this; None = all of them
    stale_minutes: Optional[int] = None


def _active(session: Session) -> list[PromoCampaign]:
    return list(session.scalars(
        select(PromoCampaign).where(PromoCampaign.active.is_(True))
        .order_by(PromoCampaign.created_at, PromoCampaign.id)).all())


@router.get("/campaigns")
def promo_list(session: Session = Depends(db_dependency)):
    return {"campaigns": [_summary(c) for c in _active(session)]}


@router.post("/campaigns")
def promo_create(body: PromoIn, authorization: Optional[str] = Header(None),
                 session: Session = Depends(db_dependency)):
    """Register a deal and read its sheet straight away. A sheet that cannot
    be read still creates the deal — with the reason attached — so the link
    can be fixed from the page instead of retyped."""
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(400, "ใส่ชื่องานก่อน")
    url = _clean_url(body.sheet_url)
    c = PromoCampaign(name=name[:255], team=(body.team or "").strip()[:255] or None,
                      sheet_url=url, created_by=_creator_info(authorization)[0], active=True)
    _apply(c, *_read(url))
    session.add(c)
    session.commit()
    session.refresh(c)
    return _detail(c)


@router.get("/campaigns/{promo_id}")
def promo_get(promo_id: int, session: Session = Depends(db_dependency)):
    return _detail(_get(session, promo_id))


@router.patch("/campaigns/{promo_id}")
def promo_update(promo_id: int, body: PromoPatch, session: Session = Depends(db_dependency)):
    c = _get(session, promo_id)
    if body.name is not None:
        if not body.name.strip():
            raise HTTPException(400, "ใส่ชื่องานก่อน")
        c.name = body.name.strip()[:255]
    if body.team is not None:
        c.team = body.team.strip()[:255] or None
    if body.sheet_url is not None:
        url = _clean_url(body.sheet_url)
        if url != c.sheet_url:
            c.sheet_url = url
            # a different file: the old snapshot no longer describes this deal
            c.data_json, c.synced_at = None, None
            _apply(c, *_read(url))
    session.commit()
    session.refresh(c)
    return _detail(c)


@router.delete("/campaigns/{promo_id}")
def promo_delete(promo_id: int, session: Session = Depends(db_dependency)):
    """Soft delete — hides the deal from the page. The team's sheet is untouched."""
    c = _get(session, promo_id)
    c.active = False
    session.commit()
    return {"status": "removed", "id": promo_id}


@router.post("/campaigns/{promo_id}/sync")
def promo_sync(promo_id: int, session: Session = Depends(db_dependency)):
    c = _get(session, promo_id)
    _apply(c, *_read(c.sheet_url))
    session.commit()
    session.refresh(c)
    return _detail(c)


@router.post("/sync")
def promo_sync_all(body: SyncAllIn, session: Session = Depends(db_dependency)):
    """Re-read every deal's sheet (or only the stale ones). Downloads run side
    by side so five sheets cost about as long as the slowest one."""
    rows = _active(session)
    due = rows
    if body.stale_minutes is not None:
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=max(0, body.stale_minutes))
        due = [c for c in rows if c.synced_at is None or c.synced_at < cutoff]
    if due:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(_read, [c.sheet_url for c in due]))
        for c, (data, error) in zip(due, results):
            _apply(c, data, error)
        session.commit()
    return {"synced": len(due), "campaigns": [_summary(c) for c in rows]}
