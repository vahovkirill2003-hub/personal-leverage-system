from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None

SQLALCHEMY_SCHEME = "postgresql+psycopg"
LIBPQ_SCHEMES = ("postgresql://", "postgres://")


def _normalize_scheme(url: str) -> str:
    """Address Psycopg 3 explicitly in a libpq-style URL.

    DATABASE_URL is consumed by psycopg directly elsewhere, so it carries a libpq
    scheme. SQLAlchemy resolves a driverless postgresql:// URL to Psycopg 2, which
    the project does not ship; only the scheme is rewritten, and an URL that already
    names the driver is returned unchanged.
    """
    for scheme in LIBPQ_SCHEMES:
        if url.startswith(scheme):
            return f"{SQLALCHEMY_SCHEME}://{url[len(scheme) :]}"
    return url


def _database_url() -> str:
    return _normalize_scheme(
        os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
    )


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        transactional_ddl=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
