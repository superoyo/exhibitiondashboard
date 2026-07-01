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
from app.models import Campaign, Kol, ReportKol, ReportPost

log = logging.getLogger("seed")

_CFG_DIR = pathlib.Path(__file__).resolve().parent.parent / "config"
CONFIG = _CFG_DIR / "kols.json"
REPORT_CONFIG = _CFG_DIR / "report_kols.json"
REPORT_POSTS_CONFIG = _CFG_DIR / "report_posts.json"
SAHAGROUP_CONFIG = _CFG_DIR / "sahagroup_kols.json"
SAHAGROUP2027_CONFIG = _CFG_DIR / "sahagroup2027_kols.json"


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


def _seed_report_roster(config_path: pathlib.Path, campaign: str) -> int:
    """Bootstrap a report roster for one campaign ONLY when that campaign is empty."""
    with session_scope() as session:
        count = session.scalar(
            select(func.count()).select_from(ReportKol).where(ReportKol.campaign == campaign)
        ) or 0
        if count > 0:
            log.info("report_kols[%s] already has %d rows — skipping.", campaign, count)
            return count
        if not config_path.exists():
            log.warning("roster config missing: %s", config_path)
            return 0
        data = json.loads(config_path.read_text(encoding="utf-8"))
        for row in data:
            username = row["username"].strip()
            session.add(ReportKol(
                username=username,
                display=row.get("display", username),
                content_group=row["group"],
                subgroup=row.get("subgroup"),
                campaign=campaign,
                url=row.get("url") or None,
                followers=row.get("followers", 0),
                active=True,
            ))
    log.info("Seeded %d report KOLs (%s) from %s.", len(data), campaign, config_path.name)
    return len(data)


def seed_report_kols_if_empty(config_path: pathlib.Path = REPORT_CONFIG) -> int:
    """Bootstrap the PAO report roster."""
    return _seed_report_roster(config_path, "pao")


def seed_sahagroup_if_empty(config_path: pathlib.Path = SAHAGROUP_CONFIG) -> int:
    """Bootstrap the Sahagroup report roster (49 KOLs, no post links yet)."""
    return _seed_report_roster(config_path, "sahagroup")


def seed_sahagroup2027_if_empty(config_path: pathlib.Path = SAHAGROUP2027_CONFIG) -> int:
    """Bootstrap the Sahagroup Fair 2027 roster (empty placeholder — fill via /kols)."""
    return _seed_report_roster(config_path, "sahagroup2027")


# ---------------------------------------------------------------------------
# Campaign metadata bootstrap — makes the 3 legacy hardcoded campaigns show up
# in the new dynamic home page on first startup. After this, new campaigns are
# created via the UI ("+ Create Campaign") and stored directly in this table.
# ---------------------------------------------------------------------------

_LEGACY_CAMPAIGNS = [
    {
        "key": "sahagroup",
        "name": "Sahagroup Fair 2026",
        "emoji": "🛍️",
        "subtitle": "Mega KOL + Micro-Nano KOL · ข้อมูลจริงจาก TikTok ผ่าน Apify",
        "groups": ["Mega Kol", "Micro-Nano Kol"],
        "subgroups": ["THE TASTE MAKERS", "THE MEMORY MAKERS", "THE VIBE MAKERS",
                      "Fashion", "Food", "Beauty", "Household Items"],
    },
    {
        "key": "pao",
        "name": "PAO Super Perfume 2026",
        "emoji": "🧴",
        "subtitle": "สรุปผล KOL/Influencer · ข้อมูลจริงจาก TikTok/Facebook ผ่าน Apify",
        "groups": ["Entertain", "Micro Local", "คู่รัก", "Facebook"],
        "subgroups": [],
    },
    {
        "key": "sahagroup2027",
        "name": "Sahagroup Fair 2027",
        "emoji": "🛍️",
        "subtitle": "แคมเปญปี 2027 · เพิ่มรายชื่อ KOL ในหน้า \"แก้ไข KOL\" แล้วกด Refresh Data",
        "groups": ["Mega Kol", "Micro-Nano Kol"],
        "subgroups": ["THE TASTE MAKERS", "THE MEMORY MAKERS", "THE VIBE MAKERS",
                      "Fashion", "Food", "Beauty", "Household Items"],
    },
]


def seed_campaigns_if_empty() -> int:
    """Insert campaign metadata for the 3 legacy campaigns on first boot.
    Idempotent: only creates rows that don't already exist (so a manually-edited
    campaign in the DB is never overwritten)."""
    created = 0
    with session_scope() as session:
        existing_keys = set(session.scalars(select(Campaign.key)).all())
        for row in _LEGACY_CAMPAIGNS:
            if row["key"] in existing_keys:
                continue
            session.add(Campaign(
                key=row["key"],
                name=row["name"],
                emoji=row["emoji"],
                subtitle=row["subtitle"],
                groups_json=json.dumps(row["groups"], ensure_ascii=False),
                subgroups_json=json.dumps(row["subgroups"], ensure_ascii=False),
                active=True,
            ))
            created += 1
    if created:
        log.info("Seeded %d legacy campaign metadata rows.", created)
    return created


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
                campaign="pao",
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
