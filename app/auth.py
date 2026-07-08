"""Wazzup / Fareast Fameline authentication (per the wazzup-authentication skill).

Two upstream operations only:
  POST /api/User/Authentication  — username+password -> session with access_token
  GET  /api/User/Profile         — bearer token -> profile + roles

The web app proxies both (avoids browser CORS) and validates bearer tokens on
protected endpoints by calling Get Profile, with a short in-memory cache so we
don't hammer the identity backend on every request.
"""
from __future__ import annotations

import logging
import os
import time

import httpx

log = logging.getLogger("auth")

WAZZUP_BASE = os.getenv("WAZZUP_BASE_URL", "https://api.fareastfamelineddb.com").rstrip("/")

_TOKEN_CACHE: dict[str, float] = {}  # token -> valid-until (epoch seconds)
_CACHE_TTL = 600  # re-validate against Wazzup every 10 minutes


def wazzup_login(username: str, password: str) -> dict:
    """Exchange credentials for the Wazzup session object. Raises ValueError
    on bad credentials, RuntimeError on upstream failure."""
    try:
        r = httpx.post(
            f"{WAZZUP_BASE}/api/User/Authentication",
            json={"authenticationName": username, "authenticationPassword": password},
            timeout=15,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("wazzup login unreachable: %s", exc)
        raise RuntimeError("sign-in failed") from exc
    if r.status_code == 401:
        raise ValueError("invalid credentials")
    if r.status_code != 200:
        log.warning("wazzup login failed: HTTP %s", r.status_code)
        raise RuntimeError("sign-in failed")
    return r.json()


def wazzup_profile(token: str) -> dict | None:
    """Fetch the signed-in user's profile; None on 401 (invalid/expired)."""
    try:
        r = httpx.get(
            f"{WAZZUP_BASE}/api/User/Profile",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("wazzup profile unreachable: %s", exc)
        return None
    if r.status_code != 200:
        return None
    data = r.json()
    # hrPassword is the user's secret — never read/forward it (skill rule)
    if isinstance(data.get("profile"), dict):
        data["profile"].pop("hrPassword", None)
    return data


def validate_token(token: str) -> bool:
    """True if the bearer token is currently accepted by Wazzup (cached)."""
    if not token:
        return False
    now = time.time()
    until = _TOKEN_CACHE.get(token)
    if until and until > now:
        return True
    if wazzup_profile(token) is not None:
        if len(_TOKEN_CACHE) > 500:  # prune stale entries
            for k, v in list(_TOKEN_CACHE.items()):
                if v <= now:
                    _TOKEN_CACHE.pop(k, None)
        _TOKEN_CACHE[token] = now + _CACHE_TTL
        return True
    _TOKEN_CACHE.pop(token, None)
    return False
