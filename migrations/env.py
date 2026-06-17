"""Alembic environment. Pulls the DB URL from app.config (env-driven)."""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app import config as app_config
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject the runtime DB URL (from DATABASE_URL env var).
# This must run at DEPLOY time, not build time — Railway's build stage has no
# database and no DATABASE_URL. If you see this error during "build", move the
# migration out of any Build Command into the start/Pre-deploy command.
if not app_config.DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is empty. Run migrations at deploy time (start command / "
        "Pre-deploy Command), and make sure the Postgres plugin is linked to this service."
    )
config.set_main_option("sqlalchemy.url", app_config.DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=app_config.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = app_config.DATABASE_URL
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
