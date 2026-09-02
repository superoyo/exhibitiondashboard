"""Channel form ("ฟอร์มช่อง"): what this channel NORMALLY does.

The Performance Analysis needs an answer to "เทียบกับคลิปอื่น ๆ ของช่องแล้วเป็นไง",
and until now the only honest material was the KOL's past jobs in our own
database — sponsored posts, and only for repeat KOLs. This module fetches the
latest ~10 posts from the channel page itself via the same Apify actors the
report refresh already uses, summarises them to medians, and caches the result
in channel_baselines for 30 days.

Cost design (the team's explicit worry was a KOL who posts constantly):
  - the sample is a FIXED CAP of CHANNEL_CLIPS posts per channel, so posting
    frequency never changes the bill;
  - the 30-day cache is global across campaigns, so a repeat KOL is free;
  - only KOLs who have actually POSTED in this campaign are fetched — someone
    still waiting has nothing to compare yet;
  - billed from Apify's real run cost into the campaign's cost table under its
    own kind ("chform"), like every other button.

Honesty guards: the KOL's tracked campaign posts (any campaign) are excluded
from the sample, so a sponsored post never inflates its own baseline; channels
whose page we cannot determine (e.g. YouTube with no profile link in the file)
are skipped, never guessed.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import statistics
from typing import Optional

from sqlalchemy import select

from app import config
from app.apify_client import (
    run_scrape_channel_fb,
    run_scrape_channel_ig,
    run_scrape_channel_tiktok,
    run_scrape_channel_yt,
)
from app.db import session_scope
from app.models import ChannelBaseline, ReportKol, ReportPost
from app.report_refresh import (
    _parse_fb_items,
    _parse_ig_items,
    _parse_report_items,
    _parse_yt_items,
    is_profile_link,
    kol_links,
)

log = logging.getLogger("channel_form")

CHANNEL_CLIPS = 10          # fixed sample cap per channel — the cost ceiling
BASELINE_TTL_DAYS = 30      # how long a fetched baseline stays fresh

_FB_SLUG = re.compile(
    r"facebook\.com/([A-Za-z0-9.\-]+)/(?:posts|videos|reel|photos)", re.I)
_FB_SLUG_BAD = {"share", "watch", "groups", "story.php", "permalink.php",
                "profile.php", "reel"}
_TT_HANDLE = re.compile(r"tiktok\.com/@([^/?#\s]+)", re.I)


def _summarise(posts: list[dict]) -> dict:
    """Medians over one channel's sample. Median, not mean — one viral clip
    must not redefine what 'normal' looks like for the channel."""
    views = [p["views"] for p in posts if p.get("views")]
    eng = [max(0, p.get("likes") or 0) + (p.get("comments") or 0)
           + (p.get("shares") or 0) + (p.get("saves") or 0) for p in posts]
    ers = [100 * e / p["views"] for p, e in zip(posts, eng) if p.get("views")]
    return {
        "sample_count": len(posts),
        "median_views": int(statistics.median(views)) if views else 0,
        "median_engagement": int(statistics.median(eng)) if eng else 0,
        "median_er_pct": round(statistics.median(ers), 2) if ers else None,
    }


def _targets(campaign: str) -> tuple[dict, set]:
    """{(username, platform): channel reference} for every POSTED KOL-platform
    in this campaign that is missing a fresh baseline, plus the set of tracked
    video_ids per username to exclude from samples."""
    cutoff = dt.datetime.now(config.TZ) - dt.timedelta(days=BASELINE_TTL_DAYS)
    with session_scope() as session:
        roster = {k.username.lower(): k for k in session.scalars(
            select(ReportKol).where(ReportKol.active.is_(True),
                                    ReportKol.campaign == campaign)).all()}
        posted: dict[tuple[str, str], str] = {}
        for p in session.scalars(select(ReportPost).where(
                ReportPost.campaign == campaign)).all():
            u = p.username.lower()
            if u in roster and (p.views or p.url):
                posted.setdefault((u, (p.platform or "").lower()), p.url or "")

        fresh = {(b.username, b.platform) for b in session.scalars(
            select(ChannelBaseline).where(ChannelBaseline.fetched_at >= cutoff)).all()}

        targets: dict[tuple[str, str], str] = {}
        for (u, plat), post_url in posted.items():
            if (u, plat) in fresh:
                continue
            k = roster[u]
            # Spec v3 (team, 2026-09-02): when a measurable KPI exists the
            # score STOPS at the KPI — comparing against the channel's other
            # posts is unfair because nobody knows which of those were
            # boosted. The baseline would go unused, so don't pay for it.
            try:
                kpis = json.loads(k.kpi_json) if k.kpi_json else []
            except ValueError:
                kpis = []
            if any(x.get("metric") in ("views", "interaction") for x in kpis):
                continue
            links = kol_links(k)
            profile = next((ln["url"] for ln in links
                            if ln.get("platform") == plat and ln.get("url")
                            and is_profile_link(plat, ln["url"])), "")
            ref: Optional[str] = None
            if plat == "tiktok":
                m = _TT_HANDLE.search(post_url or "") or _TT_HANDLE.search(profile)
                ref = (m.group(1) if m else None) or next(
                    (ln.get("handle") for ln in links
                     if ln.get("platform") == "tiktok" and ln.get("handle")), None) or u
            elif plat == "instagram":
                handle = next((ln.get("handle") for ln in links
                               if ln.get("platform") == "instagram" and ln.get("handle")), None)
                if handle:
                    ref = f"https://www.instagram.com/{handle}/"
                elif profile:
                    ref = profile
            elif plat == "youtube":
                ref = profile or None   # a watch URL carries no channel — never guess
            elif plat == "facebook":
                if profile:
                    ref = profile
                else:
                    m = _FB_SLUG.search(post_url or "")
                    if m and m.group(1).lower() not in _FB_SLUG_BAD:
                        ref = f"https://www.facebook.com/{m.group(1)}"
            if ref:
                targets[(u, plat)] = ref

        tracked: dict[str, set] = {}
        if targets:
            users = {u for (u, _p) in targets}
            for p in session.scalars(select(ReportPost).where(
                    ReportPost.username.in_(list(users)))).all():
                tracked.setdefault(p.username.lower(), set()).add(str(p.video_id))
        return targets, tracked


def _store(username: str, platform: str, posts: list[dict], tracked: dict) -> None:
    ours = tracked.get(username, set())
    sample = [p for p in posts if str(p.get("video_id")) not in ours][:CHANNEL_CLIPS]
    summary = _summarise(sample)
    with session_scope() as session:
        row = session.scalar(select(ChannelBaseline).where(
            ChannelBaseline.username == username,
            ChannelBaseline.platform == platform))
        if row is None:
            row = ChannelBaseline(username=username, platform=platform)
            session.add(row)
        row.fetched_at = dt.datetime.now(config.TZ)
        for key, val in summary.items():
            setattr(row, key, val)


def ensure_baselines(campaign: str, st=None) -> dict:
    """Fetch missing/stale baselines for this campaign's posted KOLs.
    Returns {"fetched": channels updated, "cost": summed Apify USD}.
    Best-effort per platform — one platform failing must not sink the run."""
    targets, tracked = _targets(campaign)
    if not targets:
        return {"fetched": 0, "cost": 0.0}

    total_cost, fetched = 0.0, 0

    def note(msg: str) -> None:
        if st is not None:
            st.update(message=msg)

    # TikTok + Instagram batch (one run fee for all channels); items are
    # attributed back to their channel by the author field.
    tt = {u: ref for (u, plat), ref in targets.items() if plat == "tiktok"}
    if tt:
        note(f"กำลังดึงฟอร์มช่อง TikTok ({len(tt)} ช่อง)…")
        try:
            items, meta = run_scrape_channel_tiktok(list(tt.values()), CHANNEL_CLIPS)
            total_cost += meta.get("cost_usd") or 0.0
            posts, _profiles = _parse_report_items(items)
            handle_to_user = {ref.lower(): u for u, ref in tt.items()}
            by_user: dict[str, list] = {}
            for p in posts:
                u = handle_to_user.get((p.get("username") or "").lower())
                if u:
                    by_user.setdefault(u, []).append(p)
            for u, rows in by_user.items():
                _store(u, "tiktok", rows, tracked)
                fetched += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("channel form tiktok failed: %s", exc)

    ig = {u: ref for (u, plat), ref in targets.items() if plat == "instagram"}
    if ig:
        note(f"กำลังดึงฟอร์มช่อง Instagram ({len(ig)} ช่อง)…")
        try:
            items, meta = run_scrape_channel_ig(list(ig.values()), CHANNEL_CLIPS)
            total_cost += meta.get("cost_usd") or 0.0
            posts = _parse_ig_items(items)
            handle_to_user = {ref.rstrip("/").rsplit("/", 1)[-1].lower(): u
                              for u, ref in ig.items()}
            by_user = {}
            for p in posts:
                u = handle_to_user.get((p.get("username") or "").lower())
                if u:
                    by_user.setdefault(u, []).append(p)
            for u, rows in by_user.items():
                _store(u, "instagram", rows, tracked)
                fetched += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("channel form instagram failed: %s", exc)

    # YouTube + Facebook run per channel: their actors don't return a reliable
    # channel key on every item shape, so one-channel-per-run keeps the
    # attribution certain. Start fees are $0.001 — noise.
    for (u, plat), ref in targets.items():
        if plat not in ("youtube", "facebook"):
            continue
        note(f"กำลังดึงฟอร์มช่อง {'YouTube' if plat == 'youtube' else 'Facebook'} @{u}…")
        try:
            if plat == "youtube":
                items, meta = run_scrape_channel_yt(ref, CHANNEL_CLIPS)
                posts = _parse_yt_items(items)
            else:
                items, meta = run_scrape_channel_fb(ref, CHANNEL_CLIPS)
                posts, _pr = _parse_fb_items(items)
            total_cost += meta.get("cost_usd") or 0.0
            _store(u, plat, posts, tracked)
            fetched += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("channel form %s @%s failed: %s", plat, u, exc)

    return {"fetched": fetched, "cost": round(total_cost, 4)}


def baselines_for(usernames: list[str]) -> dict:
    """{(username, platform): summary dict} for the advisor's input builder."""
    if not usernames:
        return {}
    out = {}
    with session_scope() as session:
        for b in session.scalars(select(ChannelBaseline).where(
                ChannelBaseline.username.in_(usernames))).all():
            if b.sample_count:
                out[(b.username, b.platform)] = {
                    "posts": b.sample_count,
                    "median_views": b.median_views,
                    "median_engagement": b.median_engagement,
                    "median_er_pct": b.median_er_pct,
                }
    return out
