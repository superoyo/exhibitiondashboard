"""Central configuration — reads environment variables (12-factor).

Secrets (APIFY_TOKEN, ADMIN_KEY) live ONLY in the environment / .env file,
never in source control.
"""
from __future__ import annotations

import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# Load .env for local dev. On Railway the variables are injected directly,
# so the missing-file case is harmless.
load_dotenv()


def _normalize_db_url(url: str) -> str:
    """Railway / Heroku hand out 'postgres://...'. SQLAlchemy 2.x wants
    'postgresql://...' (psycopg2 driver). Normalize so either form works."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


APIFY_TOKEN: str = os.getenv("APIFY_TOKEN", "")
DATABASE_URL: str = _normalize_db_url(os.getenv("DATABASE_URL", ""))
ADMIN_KEY: str = os.getenv("ADMIN_KEY", "")
ALERT_WEBHOOK_URL: str = os.getenv("ALERT_WEBHOOK_URL", "")

# Campaign timezone. All "run dates" are computed in this zone so that the
# 05:00 Asia/Bangkok cron lands on the correct calendar day.
TZ_NAME: str = os.getenv("TZ", "Asia/Bangkok")
TZ = ZoneInfo(TZ_NAME)

# Apify actor + tuning knobs (kept here so they are easy to find / change).
APIFY_ACTOR_ID: str = "clockworks~tiktok-scraper"
FB_ACTOR_ID: str = "apify~facebook-posts-scraper"  # campaign report Facebook posts
RESULTS_PER_PAGE: int = 20
LOOKBACK_DAYS: int = 7  # oldestPostDateUnified = today - LOOKBACK_DAYS

# Content-group brand colors (kept in sync with the frontend).
GROUP_COLORS = {
    "Fashion": "#6366f1",
    "Food": "#f59e0b",
    "Beauty": "#ec4899",
    "Household Items": "#10b981",
}


def require(name: str, value: str) -> str:
    """Fail fast with a clear message when a required secret is missing."""
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Set it in .env (local) or Railway → Variables."
        )
    return value
