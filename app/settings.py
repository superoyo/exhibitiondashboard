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


def get_cost(campaign: str) -> dict:
    raw = get_setting(_cost_key(campaign))
    if raw:
        try:
            d = json.loads(raw)
            return {"total": float(d.get("total", 0)), "count": int(d.get("count", 0)),
                    "last": d.get("last")}
        except Exception:  # noqa: BLE001
            pass
    return {"total": 0.0, "count": 0, "last": None}


def add_cost(campaign: str, cost: float | None) -> dict:
    """Accumulate one refresh run's Apify cost. cost may be None (counted as 0)."""
    c = get_cost(campaign)
    c["total"] = round(c["total"] + (cost or 0.0), 4)
    c["count"] += 1
    c["last"] = cost
    set_setting(_cost_key(campaign), json.dumps(c))
    return c


def reset_cost(campaign: str) -> None:
    set_setting(_cost_key(campaign), json.dumps({"total": 0.0, "count": 0, "last": None}))
