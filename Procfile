web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
cron-scrape: python -m app.scrape
release: alembic upgrade head
