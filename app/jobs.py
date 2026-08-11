"""Every background job's live status, in one list.

Each job writes progress into an in-memory registry keyed by a prefix — `cm:`
comments, `ti:` tie-in shots, `pf:` profile pictures, bare campaign key for the
stat refresh. Nothing ever read that registry as a whole, so a job's progress
was visible only on the page that started it: leave the page and the team could
not tell whether the work was still running, had finished, or had failed. Worse,
a second person could start the same expensive job without knowing one was
already going.

Jobs that finished recently are included on purpose. A run takes minutes, and
whoever started it has usually navigated away by the time it ends — reporting
"done" only to a page nobody is looking at means the result is never seen.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List

from sqlalchemy import select

from app import config
from app.db import session_scope
from app.models import Campaign
from app.report_refresh import REFRESH_STATES

# prefix -> (machine name, Thai label shown in the UI)
KINDS = {
    "cm:": ("comments", "วิเคราะห์คอมเมนต์"),
    "ti:": ("tiein", "หา tie-in shot"),
    "pf:": ("profiles", "ดึงรูปโปรไฟล์"),
}
REFRESH_KIND = ("refresh", "อัปเดตสถิติ")

# How long a finished job stays on screen. Long enough to be noticed on the next
# page load, short enough that yesterday's runs are not still hanging around.
KEEP_FINISHED_S = 120


def _split(key: str) -> tuple:
    for prefix, kind in KINDS.items():
        if key.startswith(prefix):
            return key[len(prefix):], kind
    return key, REFRESH_KIND


def _age_s(iso: Any) -> float:
    """Seconds since an ISO timestamp written in the campaign timezone."""
    if not iso:
        return 1e9
    try:
        stamp = dt.datetime.fromisoformat(str(iso))
    except (TypeError, ValueError):
        return 1e9
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=config.TZ)
    return (dt.datetime.now(config.TZ) - stamp).total_seconds()


def active_jobs() -> List[Dict[str, Any]]:
    """Jobs running now, plus ones that ended in the last KEEP_FINISHED_S."""
    picked = []
    for key, st in list(REFRESH_STATES.items()):
        status = st.get("status")
        if status == "running":
            pass
        elif status in ("success", "failed") and _age_s(st.get("finished_at")) <= KEEP_FINISHED_S:
            pass
        else:
            continue
        campaign, (kind, kind_label) = _split(key)
        picked.append({
            "key": key,
            "campaign": campaign,
            "kind": kind,
            "kind_label": kind_label,
            "status": status,
            "message": st.get("message") or "",
            "started_at": st.get("started_at"),
            "finished_at": st.get("finished_at"),
            "done": int(st.get("posts") or 0),
            # 0 means "not known yet" — the UI shows a count without a bar
            # rather than inventing a denominator
            "total": int(st.get("total") or 0),
            "cost_usd": st.get("cost_usd"),
        })

    if picked:
        wanted = {j["campaign"] for j in picked}
        with session_scope() as session:
            names = {
                c.key: (c.name, c.emoji)
                for c in session.scalars(
                    select(Campaign).where(Campaign.key.in_(wanted))).all()
            }
        for j in picked:
            name, emoji = names.get(j["campaign"], (j["campaign"], "📊"))
            j["campaign_name"] = name
            j["emoji"] = emoji or "📊"

    # running first, then most recently finished
    picked.sort(key=lambda j: (j["status"] != "running", _age_s(j.get("finished_at"))))
    return picked
