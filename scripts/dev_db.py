"""DEV-ONLY: start an embedded PostgreSQL (via the `pgserver` pip package) so you
can run the whole app locally without installing Postgres or Docker.

    python scripts/dev_db.py            # start server, write DATABASE_URL into .env
    python scripts/dev_db.py --stop     # stop the embedded server

The server keeps running after this script exits (cleanup_mode=None) so that
alembic / uvicorn / the scrape job — separate processes — can connect to it.
Data lives in ./.pgdata (gitignored).
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PGDATA = ROOT / ".pgdata"
ENV = ROOT / ".env"


def _write_env(database_url: str) -> None:
    lines = []
    if ENV.exists():
        lines = ENV.read_text().splitlines()
    found = False
    for i, ln in enumerate(lines):
        if re.match(r"\s*DATABASE_URL\s*=", ln):
            lines[i] = f"DATABASE_URL={database_url}"
            found = True
    if not found:
        lines.append(f"DATABASE_URL={database_url}")
    ENV.write_text("\n".join(lines) + "\n")


def start() -> None:
    import pgserver

    PGDATA.mkdir(exist_ok=True)
    server = pgserver.get_server(PGDATA, cleanup_mode=None)
    uri = server.get_uri()
    _write_env(uri)
    print("Embedded Postgres running.")
    print("DATABASE_URL written to .env:")
    print(" ", uri)


def stop() -> None:
    import pgserver

    try:
        server = pgserver.get_server(PGDATA, cleanup_mode=None)
        server.cleanup()
        print("Embedded Postgres stopped.")
    except Exception as exc:
        print(f"Could not stop server: {exc}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stop", action="store_true")
    args = ap.parse_args()
    stop() if args.stop else start()
