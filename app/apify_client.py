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
    tolerate_failure: bool = False,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Scrape SPECIFIC posts by URL — used by the campaign report refresh.

    tolerate_failure=True: if one bad URL makes the whole Apify run end FAILED,
    still return whatever posts were scraped before it failed (instead of
    discarding everything). This is what keeps a single broken link from
    wiping out the rest of the roster's data."""
    return _execute(_build_post_input(post_urls),
                    poll_interval=poll_interval, timeout_s=timeout_s,
                    tolerate_failure=tolerate_failure)


def run_scrape_profiles(
    usernames: List[str],
    *,
    poll_interval: float = 8.0,
    timeout_s: float = 300.0,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Lightweight profile scrape (resultsPerPage=1) to grab avatar + followers
    without needing post links. Used for the 'fetch profile pics' action."""
    payload = {
        "profiles": usernames,
        "resultsPerPage": 1,
        "profileScrapeSections": ["videos"],
        "profileSorting": "latest",
        "shouldDownloadVideos": False,
        "shouldDownloadCovers": False,
        "shouldDownloadSubtitles": False,
        "shouldDownloadSlideshowImages": False,
        "shouldDownloadAvatars": False,
    }
    return _execute(payload, poll_interval=poll_interval, timeout_s=timeout_s)


def run_scrape_fb(
    post_urls: List[str],
    *,
    poll_interval: float = 8.0,
    timeout_s: float = 300.0,
    tolerate_failure: bool = False,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Scrape specific Facebook posts by URL (campaign report — FB pages)."""
    payload = {"startUrls": [{"url": u} for u in post_urls], "resultsLimit": 1}
    return _execute(payload, actor_id=config.FB_ACTOR_ID,
                    poll_interval=poll_interval, timeout_s=timeout_s,
                    tolerate_failure=tolerate_failure)


def _execute(
    payload: Dict[str, Any],
    *,
    actor_id: str = config.APIFY_ACTOR_ID,
    poll_interval: float = 10.0,
    timeout_s: float = 300.0,
    tolerate_failure: bool = False,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Run the actor with the given input and return (items, run_meta).

    run_meta contains: apify_run_id, status, cost_usd, dataset_id, partial.
    Raises ApifyError on a failed/aborted/timed-out run or polling timeout —
    UNLESS tolerate_failure=True, in which case a bad terminal status still
    returns whatever dataset items were produced (meta['partial']=True), so one
    broken input URL can't discard the whole batch's good results.
    """
    from app.settings import get_apify_token

    token = config.require("APIFY_TOKEN", get_apify_token())

    with httpx.Client(timeout=60.0) as client:
        # Step 1 — start run
        start = client.post(
            f"{BASE}/acts/{actor_id}/runs",
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

        partial = False
        if status in TERMINAL_BAD:
            if not tolerate_failure:
                raise ApifyError(f"Apify run {run_id} ended with status={status}")
            # Tolerating: keep whatever the actor produced before it failed.
            partial = True
            log.warning(
                "Apify run %s ended %s — salvaging partial dataset (tolerate_failure)",
                run_id, status,
            )

        # Step 3 — fetch dataset items (runs even for a salvaged failed run)
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
        "partial": partial,
    }
    log.info("Apify run %s done: %d items, cost=%s, partial=%s", run_id, len(items), cost, partial)
    return items, meta


def oldest_date_for(today: dt.date, lookback_days: int = config.LOOKBACK_DAYS) -> str:
    """oldestPostDateUnified string (YYYY-MM-DD) = today - lookback_days."""
    return (today - dt.timedelta(days=lookback_days)).isoformat()
