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

from app.db import session_scope
from app.models import Kol

log = logging.getLogger("seed")

CONFIG = pathlib.Path(__file__).resolve().parent.parent / "config" / "kols.json"


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
