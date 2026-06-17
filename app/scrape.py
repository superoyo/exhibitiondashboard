"""Daily scrape job. Entry point for the Railway cron service:

    python -m app.scrape

The SAME run_daily_scrape() is reused by POST /api/scrape/run.
See brief section 9.

Cron note: Railway cron runs in UTC. 05:00 Asia/Bangkok (UTC+7) == 22:00 UTC
the previous day, i.e. cron expression `0 22 * * *`.
"""
from __future__ import annotations

import datetime as dt
import logging

import httpx
from sqlalchemy import select

from app import aggregate, config
from app.apify_client import ApifyError, oldest_date_for, run_scrape
from app.db import session_scope
from app.models import Kol, ScrapeRun

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("scrape")


def _today() -> dt.date:
    """Today's date in the campaign timezone (Asia/Bangkok)."""
    return dt.datetime.now(config.TZ).date()


def _alert(message: str) -> None:
    if not config.ALERT_WEBHOOK_URL:
        return
    try:
        httpx.post(config.ALERT_WEBHOOK_URL, json={"text": message}, timeout=10.0)
    except Exception as exc:  # alerting must never crash the job
        log.warning("Alert webhook failed: %s", exc)


def run_daily_scrape(run_date: dt.date | None = None) -> dict:
    """Run one full scrape cycle. Returns a small result summary dict.

    Never raises on Apify failure — records scrape_runs.status='failed' instead,
    so the cron service exits cleanly and the next day still runs.
    """
    run_date = run_date or _today()
    oldest = oldest_date_for(run_date)

    with session_scope() as session:
        usernames = [
            k.username for k in session.scalars(select(Kol).where(Kol.active.is_(True))).all()
        ]
        if not usernames:
            log.warning("No active KOLs — nothing to scrape. Did you seed the DB?")
            return {"status": "skipped", "reason": "no active KOLs"}

        run = ScrapeRun(run_date=run_date, status="running")
        session.add(run)
        session.flush()
        run_id = run.id

    log.info("Scrape start: %d KOLs, run_date=%s, oldest=%s", len(usernames), run_date, oldest)

    # --- call Apify with one retry -------------------------------------------
    items = None
    meta: dict = {}
    last_err = None
    for attempt in (1, 2):
        try:
            items, meta = run_scrape(usernames, oldest)
            break
        except (ApifyError, httpx.HTTPError) as exc:
            last_err = exc
            log.error("Apify attempt %d failed: %s", attempt, exc)

    if items is None:
        with session_scope() as session:
            run = session.get(ScrapeRun, run_id)
            run.status = "failed"
            run.error = str(last_err)[:2000]
            run.finished_at = dt.datetime.now(config.TZ)
        _alert(f"❌ KOL scrape FAILED for {run_date}: {last_err}")
        return {"status": "failed", "error": str(last_err)}

    # --- persist + aggregate -------------------------------------------------
    parsed, followers = aggregate.parse_items(items)
    with session_scope() as session:
        written = aggregate.persist_posts(session, run_date, parsed)
        aggregate.compute_kol_daily(session, run_date, followers)

        run = session.get(ScrapeRun, run_id)
        run.status = "success"
        run.apify_run_id = meta.get("apify_run_id")
        run.posts_count = written
        run.cost_usd = meta.get("cost_usd")
        run.finished_at = dt.datetime.now(config.TZ)

    log.info("Scrape done: %d posts written, cost=%s", written, meta.get("cost_usd"))
    return {
        "status": "success",
        "run_date": run_date.isoformat(),
        "posts": written,
        "cost_usd": meta.get("cost_usd"),
        "apify_run_id": meta.get("apify_run_id"),
    }


if __name__ == "__main__":
    result = run_daily_scrape()
    log.info("Result: %s", result)
    # Non-zero exit on failure so Railway marks the cron run as failed.
    raise SystemExit(0 if result.get("status") in {"success", "skipped"} else 1)
