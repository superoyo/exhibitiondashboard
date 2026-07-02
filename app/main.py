"""FastAPI app: serves the REST API and the single-file dashboard."""
from __future__ import annotations

import logging
import pathlib

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

log = logging.getLogger("main")

app = FastAPI(title="KOL TikTok Tracker", version="1.0.0")
app.include_router(api_router)


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
    return {"build": "campaign-hub-v46"}


FRONTEND_DIR = pathlib.Path(__file__).resolve().parent.parent / "frontend"
INDEX = FRONTEND_DIR / "index.html"
REPORT = FRONTEND_DIR / "report.html"
KOLS_PAGE = FRONTEND_DIR / "kols.html"
TOKEN_PAGE = FRONTEND_DIR / "token.html"
HOME_PAGE = FRONTEND_DIR / "home.html"

# HTML pages must always revalidate — otherwise browsers serve a stale shell
# after a deploy (e.g. the old report before the dynamic rewrite).
_NO_CACHE = {"Cache-Control": "no-cache, must-revalidate", "Pragma": "no-cache"}


def _page(path: pathlib.Path):
    if path.exists():
        return FileResponse(path, headers=_NO_CACHE)
    return JSONResponse({"error": f"{path.name} not found"}, status_code=404)


@app.get("/")
def index():
    """Influencer Real Time Report — home page listing all campaigns."""
    return _page(HOME_PAGE)


@app.get("/c/{campaign_key}")
def campaign_report(campaign_key: str):
    """Dynamic per-campaign report. All new campaigns use this URL pattern."""
    return _page(REPORT)


@app.get("/v/{campaign_key}")
def campaign_report_view(campaign_key: str):
    """Public, view-only campaign report (shareable link for clients). Same
    page as /c/<key> but the frontend hides all edit/refresh controls."""
    return _page(REPORT)


# ---- legacy paths kept alive so old bookmarks + shared links still work ----
@app.get("/report")
def report():
    """Legacy: PAO Super Perfume campaign report (campaign=pao)."""
    return _page(REPORT)


@app.get("/sahagroup2027")
def sahagroup2027():
    """Legacy: Sahagroup Fair 2027 report."""
    return _page(REPORT)


@app.get("/sahagroup")
def sahagroup2026():
    """Alias for the Sahagroup 2026 report (the old '/' before Campaign Hub)."""
    return _page(REPORT)


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
    """Apify token viewer/editor — open, no auth."""
    return _page(TOKEN_PAGE)


# Serve any other static assets placed in frontend/ (kept minimal; SPA is one file).
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
