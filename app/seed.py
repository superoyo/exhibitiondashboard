"""Seed / refresh the kols table from config/kols.json (idempotent upsert).

Shared by scripts/seed_kols.py (CLI) and the FastAPI startup hook, so a fresh
deploy populates the 41 KOLs automatically without a manual step.
"""
from __future__ import annotations

import json
import logging
import pathlib

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from sqlalchemy import func

from app.db import session_scope
from app.models import Kol, ReportKol, ReportPost

log = logging.getLogger("seed")

_CFG_DIR = pathlib.Path(__file__).resolve().parent.parent / "config"
CONFIG = _CFG_DIR / "kols.json"
REPORT_CONFIG = _CFG_DIR / "report_kols.json"
REPORT_POSTS_CONFIG = _CFG_DIR / "report_posts.json"


def seed_from_config(config_path: pathlib.Path = CONFIG) -> int:
    """Upsert all KOLs from the config file; deactivate any removed from it.

    Returns the number of KOLs in the file. Idempotent — safe to run on every
    deploy / startup.
    """
    data = json.loads(config_path.read_text(encoding="utf-8"))
    usernames_in_file = {row["username"].strip().lower() for row in data}

    with session_scope() as session:
        for row in data:
            username = row["username"].strip()
            session.execute(
                pg_insert(Kol)
                .values(
                    username=username,
                    display=row.get("display", username),
                    content_group=row["group"],
                    active=True,
                )
                .on_conflict_do_update(
                    index_elements=[Kol.username],
                    set_={
                        "display": row.get("display", username),
                        "content_group": row["group"],
                        "active": True,
                    },
                )
            )

        deactivated = 0
        for kol in session.scalars(select(Kol)).all():
            if kol.username.lower() not in usernames_in_file and kol.active:
                kol.active = False
                deactivated += 1

    log.info("Seeded %d KOLs from %s (deactivated %d).", len(data), config_path.name, deactivated)
    return len(data)


def seed_if_empty(config_path: pathlib.Path = CONFIG) -> int:
    """Bootstrap the kols table from config ONLY when it is empty.

    This makes the config file a first-run seed, not a source of truth that
    overwrites runtime edits on every deploy. Once KOLs exist (incl. ones
    added/edited via the /kols page), this is a no-op so edits persist.
    """
    with session_scope() as session:
        count = session.scalar(select(func.count()).select_from(Kol)) or 0
    if count > 0:
        log.info("kols table already has %d rows — skipping bootstrap seed.", count)
        return count
    return seed_from_config(config_path)


def seed_report_kols_if_empty(config_path: pathlib.Path = REPORT_CONFIG) -> int:
    """Bootstrap the report_kols roster from config ONLY when empty."""
    with session_scope() as session:
        count = session.scalar(select(func.count()).select_from(ReportKol)) or 0
        if count > 0:
            log.info("report_kols already has %d rows — skipping bootstrap.", count)
            return count
        if not config_path.exists():
            log.warning("report roster config missing: %s", config_path)
            return 0
        data = json.loads(config_path.read_text(encoding="utf-8"))
        for row in data:
            username = row["username"].strip()
            session.add(ReportKol(
                username=username,
                display=row.get("display", username),
                content_group=row["group"],
                url=row.get("url"),
                followers=row.get("followers", 0),
                active=True,
            ))
    log.info("Seeded %d report KOLs from %s.", len(data), config_path.name)
    return len(data)


def seed_report_posts_if_empty(config_path: pathlib.Path = REPORT_POSTS_CONFIG) -> int:
    """Bootstrap report_posts with the original campaign snapshot ONLY when
    empty, so /report shows data before the first 'Refresh Data' click."""
    import datetime as _dt

    from app.models import ReportPost as _RP

    with session_scope() as session:
        count = session.scalar(select(func.count()).select_from(_RP)) or 0
        if count > 0:
            log.info("report_posts already has %d rows — skipping bootstrap.", count)
            return count
        if not config_path.exists():
            return 0
        data = json.loads(config_path.read_text(encoding="utf-8"))
        for row in data:
            posted = row.get("posted_at")
            posted_dt = None
            if posted:
                try:
                    posted_dt = _dt.datetime.fromisoformat(str(posted))
                except ValueError:
                    posted_dt = None
            session.add(ReportPost(
                username=row["username"].lower(),
                video_id=row["video_id"],
                url=row.get("url"),
                cover_url=row.get("cover_url"),
                posted_at=posted_dt,
                views=row.get("views", 0), likes=row.get("likes", 0),
                comments=row.get("comments", 0), shares=row.get("shares", 0),
                saves=row.get("saves", 0),
            ))
    log.info("Seeded %d report posts from %s.", len(data), config_path.name)
    return len(data)
