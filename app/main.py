"""FastAPI app: serves the REST API and the single-file dashboard."""
from __future__ import annotations

import logging
import pathlib
import re
from html import escape as _hesc

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
    return {"build": "campaign-hub-v84"}


FRONTEND_DIR = pathlib.Path(__file__).resolve().parent.parent / "frontend"
INDEX = FRONTEND_DIR / "index.html"
REPORT = FRONTEND_DIR / "report.html"
KOLS_PAGE = FRONTEND_DIR / "kols.html"
TOKEN_PAGE = FRONTEND_DIR / "token.html"
HOME_PAGE = FRONTEND_DIR / "home.html"
LOGIN_PAGE = FRONTEND_DIR / "login.html"

# HTML pages must always revalidate — otherwise browsers serve a stale shell
# after a deploy (e.g. the old report before the dynamic rewrite).
_NO_CACHE = {"Cache-Control": "no-cache, must-revalidate", "Pragma": "no-cache"}


def _page(path: pathlib.Path):
    if path.exists():
        return FileResponse(path, headers=_NO_CACHE)
    return JSONResponse({"error": f"{path.name} not found"}, status_code=404)


def _report_with_og(campaign_key: str, inject_campaign: bool = False):
    """Serve report.html with the correct per-campaign <title> + Open Graph tags
    baked in, so link previews (LINE/Messenger/etc., which don't run JS) show the
    right campaign name/description instead of the static default."""
    if not REPORT.exists():
        return JSONResponse({"error": "report.html not found"}, status_code=404)
    html = REPORT.read_text(encoding="utf-8")
    name, emoji, subtitle = campaign_key, "📊", ""
    try:
        from app.db import session_scope
        from app.models import Campaign
        with session_scope() as s:
            c = s.get(Campaign, campaign_key)
            if c:
                name, emoji, subtitle = c.name, (c.emoji or "📊"), (c.subtitle or "")
    except Exception as exc:  # noqa: BLE001 — preview must never break the page
        log.warning("OG lookup failed for %s: %s", campaign_key, exc)
    title = f"{emoji} {name} — Campaign Report"
    desc = subtitle or "รายงานผล KOL/Influencer แบบเรียลไทม์"
    og = (f'<meta property="og:title" content="{_hesc(title)}">'
          f'<meta property="og:description" content="{_hesc(desc)}">'
          f'<meta property="og:type" content="website">'
          f'<meta name="description" content="{_hesc(desc)}">'
          f'<meta name="twitter:card" content="summary">')
    html = re.sub(r"<title>.*?</title>", f"<title>{_hesc(title)}</title>", html, count=1, flags=re.S)
    if inject_campaign:  # /v/<token> pages: tell the JS which campaign this is
        import json as _json
        og += f"<script>window.__CAMPAIGN__={_json.dumps(campaign_key)}</script>"
    html = html.replace("</head>", og + "</head>", 1)
    return HTMLResponse(html, headers=_NO_CACHE)


@app.get("/")
def index():
    """Influencer Real Time Report — home page listing all campaigns."""
    return _page(HOME_PAGE)


@app.get("/c/{campaign_key}")
def campaign_report(campaign_key: str):
    """Dynamic per-campaign report. All new campaigns use this URL pattern."""
    return _report_with_og(campaign_key)


def _serve_view(view_token: str):
    """Resolve a client view token -> campaign and serve the view-only report."""
    from sqlalchemy import select as _select

    from app.db import session_scope
    from app.models import Campaign
    key = None
    try:
        with session_scope() as s:
            c = s.execute(_select(Campaign).where(
                Campaign.view_token == view_token)).scalar_one_or_none()
            if c:
                key = c.key
    except Exception as exc:  # noqa: BLE001
        log.warning("view-token lookup failed: %s", exc)
    if not key:
        return HTMLResponse(
            "<div style='font-family:sans-serif;text-align:center;margin-top:20vh'>"
            "<h2>ไม่พบลิงก์รายงานนี้</h2><p>ลิงก์อาจถูกเปลี่ยน — "
            "กรุณาขอลิงก์ใหม่จากทีมงาน</p></div>", status_code=404)
    return _report_with_og(key, inject_campaign=True)


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


# ---- legacy paths kept alive so old bookmarks + shared links still work ----
@app.get("/report")
def report():
    """Legacy: PAO Super Perfume campaign report (campaign=pao)."""
    return _report_with_og("pao")


@app.get("/sahagroup2027")
def sahagroup2027():
    """Legacy: Sahagroup Fair 2027 report."""
    return _report_with_og("sahagroup2027")


@app.get("/sahagroup")
def sahagroup2026():
    """Alias for the Sahagroup 2026 report (the old '/' before Campaign Hub)."""
    return _report_with_og("sahagroup")


@app.get("/tracker")
def legacy_tracker():
    """Old live KOL tracker dashboard (kept reachable)."""
    return _page(INDEX)


@app.get("/kols")
def kols_page():
    """KOL roster editor (Tracker + Report) — open, no auth."""
    return _page(KOLS_PAGE)


@app.get("/token")
def token_page():
    """Apify token viewer/editor (page guarded client-side; API guarded server-side)."""
    return _page(TOKEN_PAGE)


@app.get("/login")
def login_page():
    """Sign-in page (Wazzup / Fareast Fameline identity)."""
    return _page(LOGIN_PAGE)


# Serve any other static assets placed in frontend/ (kept minimal; SPA is one file).
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
