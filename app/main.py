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
        )

        n = seed_if_empty()
        r = seed_report_kols_if_empty()
        rp = seed_report_posts_if_empty()
        log.info("Startup bootstrap: %d tracker KOLs, %d report KOLs, %d report posts.", n, r, rp)
    except Exception as exc:  # noqa: BLE001 — seeding must never crash the web
        log.warning("Startup seed skipped (%s). Run scripts/seed_kols.py manually.", exc)

@app.get("/api/version")
def version():
    """Build marker — lets us confirm which commit Railway is actually running."""
    return {"build": "report-refresh-v1"}


FRONTEND_DIR = pathlib.Path(__file__).resolve().parent.parent / "frontend"
INDEX = FRONTEND_DIR / "index.html"
REPORT = FRONTEND_DIR / "report.html"


@app.get("/")
def index():
    if INDEX.exists():
        return FileResponse(INDEX)
    return JSONResponse({"error": "frontend/index.html not found"}, status_code=404)


@app.get("/report")
def report():
    """Standalone PAO Super Perfume 2026 campaign report (self-contained snapshot)."""
    if REPORT.exists():
        return FileResponse(REPORT)
    return JSONResponse({"error": "frontend/report.html not found"}, status_code=404)


KOLS_PAGE = FRONTEND_DIR / "kols.html"


@app.get("/kols")
def kols_page():
    """KOL roster editor (Tracker + Report) — open, no auth."""
    if KOLS_PAGE.exists():
        return FileResponse(KOLS_PAGE)
    return JSONResponse({"error": "frontend/kols.html not found"}, status_code=404)


# Serve any other static assets placed in frontend/ (kept minimal; SPA is one file).
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
