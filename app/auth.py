"""Fareast Fameline authentication (skills: wazzup-authentication, iam-authentication).

Two upstream operations only:
  POST /api/User/Authentication  — username+password -> session with access_token
  GET  /api/User/Profile         — bearer token -> profile + roles

The web app proxies both (avoids browser CORS) and validates bearer tokens on
protected endpoints by calling Get Profile, with a short in-memory cache so we
don't hammer the identity backend on every request.

**Two identity providers, not one.** Wazzup issues tokens to people who sign in
with this app's own login form; IAMService issues them to people who arrive
through single sign-on (Agency Intelligence sends its users here that way).
The two speak the same Get Profile contract but do not accept each other's
tokens, so a token is checked against both before it is called invalid — IAM
first, since that is where the group is heading. Which one accepted a token is
remembered with the cache entry, so the repeat check goes straight there.

Checking only one provider is what broke the campaign list for SSO users:
Wazzup answered 401 for a perfectly valid IAM token.
"""
from __future__ import annotations

import logging
import os
import time

import httpx

log = logging.getLogger("auth")

WAZZUP_BASE = os.getenv("WAZZUP_BASE_URL", "https://api.fareastfamelineddb.com").rstrip("/")
IAM_BASE = os.getenv("IAM_BASE_URL", "https://iam.fareastfamelineddb.com").rstrip("/")

# ผู้ออก token ที่รองรับ เรียงตามลำดับที่ลอง — IAM ก่อนเพราะ SSO เป็นทางหลักแล้ว
_PROVIDERS: tuple[tuple[str, str], ...] = (("iam", IAM_BASE), ("wazzup", WAZZUP_BASE))

# token -> (valid-until epoch seconds, provider ที่รับ token ใบนี้)
_TOKEN_CACHE: dict[str, tuple[float, str]] = {}
_CACHE_TTL = 600  # re-validate every 10 minutes


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


def _profile_from(base: str, name: str, token: str) -> dict | None:
    """Ask one provider whose token this is. None = it does not accept it."""
    try:
        r = httpx.get(
            f"{base}/api/User/Profile",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001
        # ล่ม/ช้า ไม่ใช่ "ปฏิเสธ" — ผู้เรียกจะไปลองอีกเจ้าต่อ
        log.warning("%s profile unreachable: %s", name, exc)
        return None
    if r.status_code != 200:
        return None
    data = r.json()
    # hrPassword is the user's secret — never read/forward it (skill rule)
    if isinstance(data.get("profile"), dict):
        data["profile"].pop("hrPassword", None)
    return data


def fetch_profile(token: str) -> dict | None:
    """Profile of the token holder, from whichever provider issued it.

    None means no provider accepted it (or none could be reached — the caller
    treats both the same way: not signed in)."""
    if not token:
        return None
    # JWT เป็น ASCII ล้วน — token ที่มีอักขระอื่นส่งเป็น header ไม่ได้อยู่แล้ว
    # ตัดตั้งแต่ตรงนี้ ไม่งั้น httpx โยน error แล้วถูก log เป็น "unreachable" ซึ่งไม่จริง
    if not token.isascii():
        return None
    order = _PROVIDERS
    known = _TOKEN_CACHE.get(token)
    if known:
        # เคยรู้แล้วว่าใครรับ — ถามเจ้านั้นก่อน ไม่ต้องไล่ใหม่ทุกครั้ง
        order = tuple(sorted(_PROVIDERS, key=lambda p: p[0] != known[1]))
    for name, base in order:
        data = _profile_from(base, name, token)
        if data is not None:
            _remember(token, name)
            return data
    _TOKEN_CACHE.pop(token, None)
    return None


# ชื่อเดิม — ยังมีที่เรียกอยู่ และตอนนี้ครอบคลุมทั้งสองผู้ออก token
wazzup_profile = fetch_profile


def _remember(token: str, provider: str) -> None:
    now = time.time()
    if len(_TOKEN_CACHE) > 500:  # prune stale entries
        for k, (until, _) in list(_TOKEN_CACHE.items()):
            if until <= now:
                _TOKEN_CACHE.pop(k, None)
    _TOKEN_CACHE[token] = (now + _CACHE_TTL, provider)


def validate_token(token: str) -> bool:
    """True if some provider currently accepts this bearer token (cached)."""
    if not token:
        return False
    known = _TOKEN_CACHE.get(token)
    if known and known[0] > time.time():
        return True
    return fetch_profile(token) is not None
