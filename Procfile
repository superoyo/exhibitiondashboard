# The frontend is a built React SPA (apps/web/dist) served by FastAPI, so the
# build MUST run before the web process starts — see railway.json buildCommand.
#
# Migrations run at DEPLOY time (DB available), baked into the web start command —
# never at build time (no DB during build).
web: alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
cron-scrape: python -m app.scrape
