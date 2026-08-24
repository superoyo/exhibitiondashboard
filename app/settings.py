"""Runtime-editable settings stored in the app_settings table.

Currently used for the Apify token so an expired key can be swapped from the
/token page without a redeploy. Falls back to the APIFY_TOKEN env var when no
DB override is set.
"""
from __future__ import annotations

import json
import logging

from app import config
from app.db import session_scope
from app.models import AppSetting

log = logging.getLogger("settings")

APIFY_TOKEN_KEY = "apify_token"


def get_setting(key: str) -> str | None:
    try:
        with session_scope() as session:
            row = session.get(AppSetting, key)
            return row.value if row else None
    except Exception as exc:  # noqa: BLE001 — never crash callers on DB hiccup
        log.warning("get_setting(%s) failed: %s", key, exc)
        return None


def set_setting(key: str, value: str) -> None:
    with session_scope() as session:
        row = session.get(AppSetting, key)
        if row:
            row.value = value
        else:
            session.add(AppSetting(key=key, value=value))


def get_apify_token() -> str:
    """DB override → env var. Used by every Apify call."""
    return (get_setting(APIFY_TOKEN_KEY) or config.APIFY_TOKEN or "").strip()


def apify_token_source() -> str:
    return "database" if get_setting(APIFY_TOKEN_KEY) else "env"


ANTHROPIC_KEY_KEY = "anthropic_api_key"


def get_anthropic_key() -> str:
    """DB override → env var — same pattern as the Apify token, so the team
    can swap the Claude key from the /token page without touching Railway."""
    import os
    return (get_setting(ANTHROPIC_KEY_KEY) or os.getenv("ANTHROPIC_API_KEY", "")).strip()


def anthropic_key_source() -> str:
    return "database" if get_setting(ANTHROPIC_KEY_KEY) else "env"


def mask_token(tok: str) -> str:
    """Show only enough to recognise the key — e.g. 'apify_••••••••cD3f'."""
    tok = (tok or "").strip()
    if not tok:
        return ""
    if len(tok) <= 10:
        return tok[:2] + "•" * 6
    return f"{tok[:6]}{'•' * 8}{tok[-4:]}"


# ---- cumulative Apify spend per campaign (from real run cost) ----------------

def _cost_key(campaign: str) -> str:
    return f"refresh_cost:{campaign}"


# Which button a charge came from. Kept here rather than in each job so the
# strings the UI groups by cannot drift from the strings the jobs write.
COST_KINDS = {
    "refresh": "อัปเดตสถิติ",
    "comments": "วิเคราะห์คอมเมนต์",
    # tiein has no button of its own — it is step 1 of 📥 PowerPoint (see
    # usePptxExport). Labelled that way so the team reads this line as part of
    # the cost of producing the deck, not as some job they never pressed.
    "tiein": "หา tie-in shot (ขั้นแรกของปุ่ม PowerPoint)",
    "profiles": "ดึงรูปโปรไฟล์",
}


def get_cost(campaign: str) -> dict:
    """Accumulated Apify spend for a campaign, split by which job spent it.

    `by_kind` is absent from records written before the split existed. Those
    amounts stay in `total`, so `total` minus the sum of `by_kind` is the older,
    unattributable spend — reported as its own line rather than dropped or
    silently folded into one of the buttons."""
    empty = {"total": 0.0, "count": 0, "last": None, "by_kind": {}}
    raw = get_setting(_cost_key(campaign))
    if raw:
        try:
            d = json.loads(raw)
            by_kind = d.get("by_kind") or {}
            return {
                "total": float(d.get("total", 0)),
                "count": int(d.get("count", 0)),
                "last": d.get("last"),
                "by_kind": {
                    k: {"total": round(float(v.get("total", 0)), 4),
                        "count": int(v.get("count", 0))}
                    for k, v in by_kind.items() if k in COST_KINDS
                },
            }
        except Exception:  # noqa: BLE001
            pass
    return empty


def add_cost(campaign: str, cost: float | None, kind: str | None = None) -> dict:
    """Record one run's Apify cost. cost may be None (counted as 0).

    `kind` names the job that spent it — one of COST_KINDS. A run counted
    without a kind still lands in the total, which keeps the number honest even
    if a future job forgets to pass one."""
    c = get_cost(campaign)
    c["total"] = round(c["total"] + (cost or 0.0), 4)
    c["count"] += 1
    c["last"] = cost
    if kind in COST_KINDS:
        slot = c["by_kind"].setdefault(kind, {"total": 0.0, "count": 0})
        slot["total"] = round(slot["total"] + (cost or 0.0), 4)
        slot["count"] += 1
    set_setting(_cost_key(campaign), json.dumps(c))
    return c


def reset_cost(campaign: str) -> None:
    set_setting(_cost_key(campaign),
                json.dumps({"total": 0.0, "count": 0, "last": None, "by_kind": {}}))
