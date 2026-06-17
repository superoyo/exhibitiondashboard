# Migrations run at DEPLOY time (DB available), baked into the web start command —
# never at build time (no DB during build).
web: alembic upgrade head && python scripts/seed_kols.py && uvicorn app.main:app --host 0.0.0.0 --port $PORT
cron-scrape: python -m app.scrape
