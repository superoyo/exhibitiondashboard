"""Seed / refresh the kols table from config/kols.json (idempotent upsert by username).

Run:  python scripts/seed_kols.py
Edit config/kols.json to add/remove/deactivate KOLs, then re-run.
KOLs present in the DB but missing from the file are set active=false (kept for history).
"""
from __future__ import annotations

import json
import pathlib
import sys

# allow running as a standalone script
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from app.db import session_scope  # noqa: E402
from app.models import Kol  # noqa: E402

CONFIG = pathlib.Path(__file__).resolve().parent.parent / "config" / "kols.json"


def main() -> None:
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    usernames_in_file = {row["username"].strip().lower() for row in data}

    with session_scope() as session:
        for row in data:
            username = row["username"].strip()
            stmt = (
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
            session.execute(stmt)

        # Deactivate KOLs that were removed from the file (keep their history).
        existing = session.scalars(select(Kol)).all()
        deactivated = 0
        for kol in existing:
            if kol.username.lower() not in usernames_in_file and kol.active:
                kol.active = False
                deactivated += 1

    print(f"Seeded {len(data)} KOLs from {CONFIG.name}. Deactivated {deactivated} removed KOL(s).")


if __name__ == "__main__":
    main()
