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
            seed_if_empty,
            seed_report_kols_if_empty,
            seed_report_posts_if_empty,
            seed_sahagroup_if_empty,
        )

        n = seed_if_empty()
        r = seed_report_kols_if_empty()
        rp = seed_report_posts_if_empty()
        sg = seed_sahagroup_if_empty()
        log.info("Startup bootstrap: %d tracker, %d PAO KOLs, %d PAO posts, %d Sahagroup KOLs.", n, r, rp, sg)
    except Exception as exc:  # noqa: BLE001 — seeding must never crash the web
        log.warning("Startup seed skipped (%s). Run scripts/seed_kols.py manually.", exc)

@app.get("/api/version")
def version():
    """Build marker — lets us confirm which commit Railway is actually running."""
    return {"build": "profile-pics-v10"}


FRONTEND_DIR = pathlib.Path(__file__).resolve().parent.parent / "frontend"
INDEX = FRONTEND_DIR / "index.html"
REPORT = FRONTEND_DIR / "report.html"
KOLS_PAGE = FRONTEND_DIR / "kols.html"
TOKEN_PAGE = FRONTEND_DIR / "token.html"

# HTML pages must always revalidate — otherwise browsers serve a stale shell
# after a deploy (e.g. the old report before the dynamic rewrite).
_NO_CACHE = {"Cache-Control": "no-cache, must-revalidate", "Pragma": "no-cache"}


def _page(path: pathlib.Path):
    if path.exists():
        return FileResponse(path, headers=_NO_CACHE)
    return JSONResponse({"error": f"{path.name} not found"}, status_code=404)


@app.get("/")
def index():
    """Sahagroup Fair campaign report (PAO-pattern, campaign=sahagroup)."""
    return _page(REPORT)


@app.get("/report")
def report():
    """PAO Super Perfume campaign report (campaign=pao)."""
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
