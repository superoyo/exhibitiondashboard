"""FastAPI app: serves the REST API and the single-file dashboard."""
from __future__ import annotations

import json
import logging
import pathlib
import re
from html import escape as _hesc
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app.api.routes import router as api_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

log = logging.getLogger("main")

app = FastAPI(title="KOL TikTok Tracker", version="1.0.0")
app.include_router(api_router)


# ---------------------------------------------------------------------------
# Auth gate (Wazzup bearer token) for mutating / costly / internal API calls.
# View-only client pages must keep working WITHOUT login, so the endpoints
# they read stay open. Pages themselves are guarded client-side (/static/auth.js).
# ---------------------------------------------------------------------------

_OPEN_API_PREFIXES = (
    "/api/auth/",           # login/profile proxy
    "/api/img",             # image cache (view pages)
    "/api/report/data",     # report stats (view pages)
    "/api/report/tiein/status",  # read-only job progress (diagnostics)
    "/api/summary", "/api/trend", "/api/posts", "/api/kols/",  # legacy tracker reads
)
_OPEN_API_EXACT = {"/api/version", "/api/health", "/api/scrape/run"}  # scrape/run has X-ADMIN-KEY


def _needs_auth(method: str, path: str) -> bool:
    if not path.startswith("/api/"):
        return False
    if path in _OPEN_API_EXACT or path.startswith(_OPEN_API_PREFIXES):
        return False
    # single-campaign metadata is read by view-only pages for the title
    if method == "GET" and re.fullmatch(r"/api/campaigns/[^/]+", path):
        return False
    return True


@app.middleware("http")
async def _auth_guard(request: Request, call_next):
    if _needs_auth(request.method, request.url.path):
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        from app.auth import validate_token
        ok = bool(token) and await run_in_threadpool(validate_token, token)
        if not ok:
            return JSONResponse({"detail": "unauthorized — กรุณาเข้าสู่ระบบ"}, status_code=401)
    return await call_next(request)


@app.on_event("startup")
def _seed_on_startup() -> None:
    """Best-effort seed of the KOL master list on boot. Never blocks startup —
    if it fails (e.g. DB not ready), the web still serves and logs the error."""
    try:
        from app.seed import (
            seed_campaigns_if_empty,
            seed_if_empty,
            seed_report_kols_if_empty,
            seed_report_posts_if_empty,
            seed_sahagroup_if_empty,
            seed_sahagroup2027_if_empty,
        )

        n = seed_if_empty()
        r = seed_report_kols_if_empty()
        rp = seed_report_posts_if_empty()
        sg = seed_sahagroup_if_empty()
        sg27 = seed_sahagroup2027_if_empty()
        cm = seed_campaigns_if_empty()
        log.info(
            "Startup bootstrap: %d tracker, %d PAO KOLs, %d PAO posts, %d Sahagroup KOLs, %d Sahagroup2027 KOLs, %d campaign meta.",
            n, r, rp, sg, sg27, cm,
        )
    except Exception as exc:  # noqa: BLE001 — seeding must never crash the web
        log.warning("Startup seed skipped (%s). Run scripts/seed_kols.py manually.", exc)

@app.get("/api/version")
def version():
    """Build marker — lets us confirm which commit Railway is actually running."""
    return {"build": "campaign-hub-v97"}


ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB_DIST = ROOT / "apps" / "web" / "dist"       # built React SPA (Vite output)
LEGACY_DIR = ROOT / "frontend"                  # pre-migration static pages

# HTML must always revalidate — otherwise browsers serve a stale shell after a
# deploy. Hashed assets are the opposite: their name changes when they do, so
# they can be cached forever.
_NO_CACHE = {"Cache-Control": "no-cache, must-revalidate", "Pragma": "no-cache"}
_IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}

_DEFAULT_TITLE = "Influencer Real Time Report"
_DEFAULT_DESC = "รายงานผล KOL/Influencer แบบเรียลไทม์"


def _shell_html() -> Optional[str]:
    """The built SPA shell, or None when the frontend has not been built."""
    index = WEB_DIST / "index.html"
    if not index.exists():
        return None
    return index.read_text(encoding="utf-8")


def _campaign_meta(campaign_key: str) -> tuple[str, str, str]:
    """(name, emoji, subtitle) for a campaign — falls back to the key itself."""
    name, emoji, subtitle = campaign_key, "📊", ""
    try:
        from app.db import session_scope
        from app.models import Campaign
        with session_scope() as s:
            c = s.get(Campaign, campaign_key)
            if c:
                name, emoji, subtitle = c.name, (c.emoji or "📊"), (c.subtitle or "")
    except Exception as exc:  # noqa: BLE001 — a preview must never break the page
        log.warning("OG lookup failed for %s: %s", campaign_key, exc)
    return name, emoji, subtitle


def _serve_shell(campaign_key: Optional[str] = None, inject_campaign: bool = False):
    """Serve the SPA shell.

    When a campaign is given, its <title> + Open Graph tags are baked in
    server-side. This is NOT cosmetic: LINE, Messenger and Facebook crawlers do
    not execute JavaScript, so without this every shared report link would
    preview as the generic app title. React overwrites the title on mount, so
    real users see the same thing either way.

    `inject_campaign` additionally exposes `window.__CAMPAIGN__` — the only way a
    /v/<token> page can learn which campaign it is, since the token in the URL is
    deliberately random rather than the campaign key.
    """
    html = _shell_html()
    if html is None:
        # The frontend build is missing. Fall back to the legacy pages if they are
        # still present so the site stays up, and make the cause loud in the logs.
        log.error(
            "apps/web/dist/index.html not found — the frontend was not built. "
            "Run `pnpm install && pnpm --filter @kol/web build` (see railway.json)."
        )
        legacy = LEGACY_DIR / ("report.html" if campaign_key else "home.html")
        if legacy.exists():
            return FileResponse(legacy, headers=_NO_CACHE)
        return JSONResponse({"error": "frontend not built"}, status_code=503)

    return HTMLResponse(_inject_meta(html, campaign_key, inject_campaign),
                        headers=_NO_CACHE)


def _inject_meta(html: str, campaign_key: Optional[str] = None,
                 inject_campaign: bool = False) -> str:
    """Bake the per-campaign <title> + Open Graph tags into an HTML page.

    Shared by the SPA shell and the legacy pages that have not been ported yet,
    so a shared link previews the same either way.
    """
    title, desc = _DEFAULT_TITLE, _DEFAULT_DESC
    if campaign_key:
        name, emoji, subtitle = _campaign_meta(campaign_key)
        title = f"{emoji} {name} — Campaign Report"
        desc = subtitle or _DEFAULT_DESC

    head = (
        f'<meta property="og:title" content="{_hesc(title)}">'
        f'<meta property="og:description" content="{_hesc(desc)}">'
        f'<meta property="og:type" content="website">'
        f'<meta name="description" content="{_hesc(desc)}">'
        f'<meta name="twitter:card" content="summary">'
    )
    if inject_campaign and campaign_key:
        head += f"<script>window.__CAMPAIGN__={json.dumps(campaign_key)}</script>"

    html = re.sub(r"<title>.*?</title>", f"<title>{_hesc(title)}</title>",
                  html, count=1, flags=re.S)
    # Drop the page's placeholder description so we don't emit two of them.
    html = re.sub(r'<meta\s+name="description"[^>]*>', "", html, count=1)
    return html.replace("</head>", head + "</head>", 1)


def _serve_legacy(name: str, campaign_key: Optional[str] = None,
                  inject_campaign: bool = False):
    """Serve a pre-migration page from frontend/.

    Only for views the React app does not implement yet (see the /vi/ and
    /kol-list routes). Everything else goes through _serve_shell.
    """
    page = LEGACY_DIR / name
    if not page.exists():
        return JSONResponse({"error": f"{name} not found"}, status_code=404)
    return HTMLResponse(
        _inject_meta(page.read_text(encoding="utf-8"), campaign_key, inject_campaign),
        headers=_NO_CACHE,
    )


def _campaign_for_view_token(view_token: str) -> Optional[str]:
    """Client/influencer links carry a random token, not the campaign key."""
    from sqlalchemy import select as _select

    from app.db import session_scope
    from app.models import Campaign
    try:
        with session_scope() as s:
            c = s.execute(_select(Campaign).where(
                Campaign.view_token == view_token)).scalar_one_or_none()
            return c.key if c else None
    except Exception as exc:  # noqa: BLE001
        log.warning("view-token lookup failed: %s", exc)
        return None


def _view_not_found():
    return HTMLResponse(
        "<div style='font-family:sans-serif;text-align:center;margin-top:20vh'>"
        "<h2>ไม่พบลิงก์รายงานนี้</h2><p>ลิงก์อาจถูกเปลี่ยน — "
        "กรุณาขอลิงก์ใหม่จากทีมงาน</p></div>", status_code=404)


def _serve_view(view_token: str):
    """Resolve a client view token -> campaign, then serve the view-only report."""
    key = _campaign_for_view_token(view_token)
    if not key:
        return _view_not_found()
    return _serve_shell(key, inject_campaign=True)


def _serve_influencer_view(view_token: str):
    """Influencer link (/vi/) — still the legacy report page.

    The React app has neither a /vi route nor the influencer-only layout
    (report.html switches on body.influencer-view), so serving the SPA shell
    here would render the not-found page and lose the feature. Point this at
    _serve_view once the influencer view is ported.
    """
    key = _campaign_for_view_token(view_token)
    if not key:
        return _view_not_found()
    return _serve_legacy("report.html", key, inject_campaign=True)


# ---------------------------------------------------------------------------
# Page routes. Each one returns the same SPA shell; React Router decides what to
# render. They are declared explicitly (rather than left to the catch-all) so the
# per-campaign Open Graph tags above can be applied where they matter.
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return _serve_shell()


@app.get("/c/{campaign_key}")
def campaign_report(campaign_key: str):
    """Dynamic per-campaign report. All new campaigns use this URL pattern."""
    return _serve_shell(campaign_key)


@app.get("/v/{view_token}")
def campaign_report_view(view_token: str):
    """Public, view-only report. The path segment is a RANDOM view token (not
    the campaign key) so links can't be enumerated."""
    return _serve_view(view_token)


@app.get("/v/{slug}/{view_token}")
def campaign_report_view_named(slug: str, view_token: str):
    """Same as /v/<token> but with a readable campaign-name slug in front
    (cosmetic only — resolution is by the token; the slug is ignored)."""
    return _serve_view(view_token)


@app.get("/vi/{view_token}")
def campaign_report_view_influencer(view_token: str):
    """Public, view-only report for INFLUENCERS. Same content as /v/ but a
    distinct entry point (URL namespace) so influencer links stay separate
    from client links and can be evolved independently later."""
    return _serve_influencer_view(view_token)


@app.get("/vi/{slug}/{view_token}")
def campaign_report_view_influencer_named(slug: str, view_token: str):
    """Same as /vi/<token> but with a readable campaign-name slug in front
    (cosmetic only — resolution is by the token; the slug is ignored)."""
    return _serve_influencer_view(view_token)


# ---- legacy paths kept alive so old bookmarks + shared links still work ----
# React redirects these to /c/<key> on mount; the server still applies the right
# campaign's OG tags so link previews keep working for crawlers.
@app.get("/report")
def report():
    """Legacy: PAO Super Perfume campaign report (campaign=pao)."""
    return _serve_shell("pao")


@app.get("/sahagroup2027")
def sahagroup2027():
    """Legacy: Sahagroup Fair 2027 report."""
    return _serve_shell("sahagroup2027")


@app.get("/sahagroup")
def sahagroup2026():
    """Alias for the Sahagroup 2026 report (the old '/' before Campaign Hub)."""
    return _serve_shell("sahagroup")


@app.get("/tracker")
def legacy_tracker():
    """Live KOL tracker dashboard."""
    return _serve_shell()


@app.get("/kols")
def kols_page():
    """KOL roster editor."""
    return _serve_shell()


@app.get("/kol-list")
def kol_list_page():
    """KOL directory across all campaigns (page guarded client-side).

    Still the legacy page — the React app does not implement this view yet.
    (FRONTEND_DIR became LEGACY_DIR in the migration; the merge left this
    reference dangling, which crashed the route.)
    """
    return _serve_legacy("kol-list.html")


@app.get("/token")
def token_page():
    """Apify token viewer/editor."""
    return _serve_shell()


@app.get("/login")
def login_page():
    """Sign-in page (Wazzup / Fareast Fameline identity)."""
    return _serve_shell()


# Legacy asset path: the pre-migration pages loaded /static/logo.png and
# /static/auth.js. Kept mounted so any external reference still resolves.
if LEGACY_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(LEGACY_DIR)), name="static")


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    """Serve built assets, and the SPA shell for any other client-side route.

    Declared last so it only sees paths nothing above matched.
    """
    # Never answer an unmatched /api/ path with HTML — an API client expects
    # JSON, and returning a page would turn a typo into a confusing parse error.
    if full_path.startswith("api/"):
        return JSONResponse({"detail": "not found"}, status_code=404)

    if WEB_DIST.exists() and full_path:
        candidate = (WEB_DIST / full_path).resolve()
        # Path-traversal guard: the resolved path must stay inside the build dir.
        if candidate.is_file() and candidate.is_relative_to(WEB_DIST.resolve()):
            # Vite content-hashes everything under /assets, so those are
            # immutable; anything else (logo.png, favicons) may be replaced.
            headers = _IMMUTABLE if full_path.startswith("assets/") else _NO_CACHE
            return FileResponse(candidate, headers=headers)

    return _serve_shell()
