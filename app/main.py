"""FastAPI app: serves the REST API and the single-file dashboard."""
from __future__ import annotations

import logging
import pathlib

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="KOL TikTok Tracker", version="1.0.0")
app.include_router(api_router)

FRONTEND_DIR = pathlib.Path(__file__).resolve().parent.parent / "frontend"
INDEX = FRONTEND_DIR / "index.html"


@app.get("/")
def index():
    if INDEX.exists():
        return FileResponse(INDEX)
    return JSONResponse({"error": "frontend/index.html not found"}, status_code=404)


# Serve any other static assets placed in frontend/ (kept minimal; SPA is one file).
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
