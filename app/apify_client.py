"""Apify client for the clockworks/tiktok-scraper actor.

Uses the async pattern (start run → poll → fetch dataset) rather than run-sync,
because 41 profiles take ~90s which can exceed the sync endpoint's timeout.
See brief section 6.
"""
from __future__ import annotations

import datetime as dt
import logging
import time
from typing import Any, Dict, List, Tuple

import httpx

from app import config

log = logging.getLogger("apify")

BASE = "https://api.apify.com/v2"
TERMINAL_OK = {"SUCCEEDED"}
TERMINAL_BAD = {"FAILED", "ABORTED", "TIMED-OUT", "TIMED_OUT"}


class ApifyError(RuntimeError):
    pass


def _build_input(usernames: List[str], oldest_date: str) -> Dict[str, Any]:
    """Actor input payload (brief section 6.2). All media downloads disabled to
    keep cost/time down; date filter limits to the trailing window."""
    return {
        "profiles": usernames,
        "resultsPerPage": config.RESULTS_PER_PAGE,
        "profileScrapeSections": ["videos"],
        "profileSorting": "latest",
        "excludePinnedPosts": False,
        "oldestPostDateUnified": oldest_date,
        "shouldDownloadVideos": False,
        "shouldDownloadCovers": False,
        "shouldDownloadSubtitles": False,
        "shouldDownloadSlideshowImages": False,
        "shouldDownloadAvatars": False,
    }


def run_scrape(
    usernames: List[str],
    oldest_date: str,
    *,
    poll_interval: float = 10.0,
    timeout_s: float = 300.0,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Scrape KOL PROFILES (trailing window) — used by the live tracker."""
    return _execute(_build_input(usernames, oldest_date),
                    poll_interval=poll_interval, timeout_s=timeout_s)


def _build_post_input(post_urls: List[str]) -> Dict[str, Any]:
    """Actor input to scrape SPECIFIC posts by URL (campaign report mode)."""
    return {
        "postURLs": post_urls,
        "shouldDownloadVideos": False,
        "shouldDownloadCovers": False,
        "shouldDownloadSubtitles": False,
        "shouldDownloadSlideshowImages": False,
        "shouldDownloadAvatars": False,
    }


def run_scrape_posts(
    post_urls: List[str],
    *,
    poll_interval: float = 10.0,
    timeout_s: float = 300.0,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Scrape SPECIFIC posts by URL — used by the campaign report refresh."""
    return _execute(_build_post_input(post_urls),
                    poll_interval=poll_interval, timeout_s=timeout_s)


def _execute(
    payload: Dict[str, Any],
    *,
    poll_interval: float = 10.0,
    timeout_s: float = 300.0,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Run the actor with the given input and return (items, run_meta).

    run_meta contains: apify_run_id, status, cost_usd, dataset_id.
    Raises ApifyError on a failed/aborted/timed-out run or polling timeout.
    """
    token = config.require("APIFY_TOKEN", config.APIFY_TOKEN)

    with httpx.Client(timeout=60.0) as client:
        # Step 1 — start run
        start = client.post(
            f"{BASE}/acts/{config.APIFY_ACTOR_ID}/runs",
            params={"token": token},
            json=payload,
        )
        start.raise_for_status()
        run = start.json()["data"]
        run_id = run["id"]
        dataset_id = run["defaultDatasetId"]
        log.info("Apify run started: run_id=%s dataset=%s", run_id, dataset_id)

        # Step 2 — poll until terminal
        deadline = time.monotonic() + timeout_s
        status = run.get("status", "READY")
        last = run
        while status not in TERMINAL_OK and status not in TERMINAL_BAD:
            if time.monotonic() > deadline:
                raise ApifyError(f"Apify run {run_id} polling timed out after {timeout_s}s (last status={status})")
            time.sleep(poll_interval)
            r = client.get(f"{BASE}/actor-runs/{run_id}", params={"token": token})
            r.raise_for_status()
            last = r.json()["data"]
            status = last.get("status")
            log.info("Apify run %s status=%s", run_id, status)

        if status in TERMINAL_BAD:
            raise ApifyError(f"Apify run {run_id} ended with status={status}")

        # Step 3 — fetch dataset items
        items_resp = client.get(
            f"{BASE}/datasets/{dataset_id}/items",
            params={"token": token, "clean": "true"},
        )
        items_resp.raise_for_status()
        items = items_resp.json()

    cost = last.get("usageTotalUsd")
    meta = {
        "apify_run_id": run_id,
        "status": status,
        "cost_usd": float(cost) if cost is not None else None,
        "dataset_id": dataset_id,
    }
    log.info("Apify run %s done: %d items, cost=%s", run_id, len(items), cost)
    return items, meta


def oldest_date_for(today: dt.date, lookback_days: int = config.LOOKBACK_DAYS) -> str:
    """oldestPostDateUnified string (YYYY-MM-DD) = today - lookback_days."""
    return (today - dt.timedelta(days=lookback_days)).isoformat()
