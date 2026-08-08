import asyncio

from fastapi import Response, status

from pls import health
from pls.health import ReadinessResult
from pls.processes import web


def test_liveness_has_no_external_dependencies(monkeypatch) -> None:
    async def fail_if_called(*args, **kwargs):
        raise AssertionError("liveness must not check database or other external services")

    monkeypatch.setattr(health, "_database_and_migrations_ready", fail_if_called)

    assert asyncio.run(web.live()) == {"status": "alive"}


def test_readiness_fails_closed_for_missing_secrets_and_policies(monkeypatch) -> None:
    async def database_ready(env):
        return True, True

    monkeypatch.setattr(health, "_database_and_migrations_ready", database_ready)

    result = asyncio.run(health.readiness({"DATABASE_URL": "postgresql://synthetic"}))

    assert result.ready is False
    assert result.checks == {
        "database": True,
        "migrations": True,
        "secrets": False,
        "policy_versions": False,
    }


def test_readiness_does_not_require_model_provider_configuration(monkeypatch) -> None:
    async def database_ready(env):
        return True, True

    monkeypatch.setattr(health, "_database_and_migrations_ready", database_ready)
    env = {
        "DATABASE_URL": "postgresql://synthetic",
        "PLS_TELEGRAM_BOT_TOKEN": "synthetic-token",
        "PLS_TELEGRAM_WEBHOOK_SECRET": "synthetic-secret",
        "PLS_PRIORITY_POLICY_VERSION": "10-decisions-log-v2:PLS-011",
        "PLS_GUARD_POLICY_VERSION": "03-state-machine-v2",
        "PLS_GATE_POLICY_VERSION": "05-gates-v2",
    }

    result = asyncio.run(health.readiness(env))

    assert result == ReadinessResult(
        ready=True,
        checks={
            "database": True,
            "migrations": True,
            "secrets": True,
            "policy_versions": True,
        },
    )


def test_ready_endpoint_returns_503_when_readiness_fails(monkeypatch) -> None:
    async def not_ready():
        return ReadinessResult(
            ready=False,
            checks={
                "database": False,
                "migrations": False,
                "secrets": True,
                "policy_versions": True,
            },
        )

    monkeypatch.setattr(web, "readiness", not_ready)
    response = Response()

    payload = asyncio.run(web.ready(response))

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert payload["status"] == "not_ready"
