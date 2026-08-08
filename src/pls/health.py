"""Health, liveness, and readiness contracts for PLS runtime processes."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

import psycopg

REQUIRED_SECRETS = (
    "PLS_TELEGRAM_BOT_TOKEN",
    "PLS_TELEGRAM_WEBHOOK_SECRET",
)
REQUIRED_POLICY_VERSIONS = (
    "PLS_PRIORITY_POLICY_VERSION",
    "PLS_GUARD_POLICY_VERSION",
    "PLS_GATE_POLICY_VERSION",
)


@dataclass(frozen=True)
class ReadinessResult:
    """Result of readiness checks without exposing secret values."""

    ready: bool
    checks: dict[str, bool]


def liveness() -> dict[str, str]:
    """Report in-process liveness without touching any external dependency."""
    return {"status": "alive"}


def _required_values_present(env: Mapping[str, str], names: tuple[str, ...]) -> bool:
    return all(bool(env.get(name, "").strip()) for name in names)


async def _database_and_migrations_ready(env: Mapping[str, str]) -> tuple[bool, bool]:
    database_url = env.get("DATABASE_URL", "").strip()
    if not database_url:
        return False, False

    expected_head = env.get("PLS_EXPECTED_MIGRATION_HEAD", "").strip()
    try:
        connection = await psycopg.AsyncConnection.connect(database_url, connect_timeout=2)
        async with connection:
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT 1")
                database_ready = (await cursor.fetchone()) == (1,)

                await cursor.execute("SELECT to_regclass('public.alembic_version')")
                migration_table = (await cursor.fetchone())[0]
                if migration_table is None:
                    migrations_ready = expected_head == ""
                elif expected_head == "":
                    migrations_ready = False
                else:
                    await cursor.execute("SELECT version_num FROM alembic_version")
                    applied_heads = {row[0] for row in await cursor.fetchall()}
                    migrations_ready = applied_heads == {expected_head}
    except (psycopg.Error, OSError, ValueError):
        return False, False

    return database_ready, migrations_ready


async def readiness(env: Mapping[str, str] | None = None) -> ReadinessResult:
    """Check the dependencies that gate service readiness.

    Model providers are deliberately absent: provider outages degrade model jobs
    but do not make the PLS service itself unready.
    """
    runtime_env = os.environ if env is None else env
    database_ready, migrations_ready = await _database_and_migrations_ready(runtime_env)
    checks = {
        "database": database_ready,
        "migrations": migrations_ready,
        "secrets": _required_values_present(runtime_env, REQUIRED_SECRETS),
        "policy_versions": _required_values_present(runtime_env, REQUIRED_POLICY_VERSIONS),
    }
    return ReadinessResult(ready=all(checks.values()), checks=checks)
