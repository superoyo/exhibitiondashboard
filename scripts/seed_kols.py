"""Seed / refresh the kols table from config/kols.json (idempotent).

Run:  python scripts/seed_kols.py
Edit config/kols.json to add/remove KOLs, then re-run (or just redeploy —
the web service also seeds on startup).
"""
from __future__ import annotations

import pathlib
import sys

# allow running as a standalone script
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.seed import seed_from_config  # noqa: E402


def main() -> None:
    n = seed_from_config()
    print(f"Seeded {n} KOLs.")


if __name__ == "__main__":
    main()
