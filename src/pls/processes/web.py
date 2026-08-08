"""Web process entrypoint and operational probes."""

from fastapi import FastAPI, Response, status

from pls.health import liveness, readiness

app = FastAPI(title="Personal Leverage System", docs_url=None, redoc_url=None)


@app.get("/health/live")
async def live() -> dict[str, str]:
    """Return process/event-loop liveness without external dependency checks."""
    return liveness()


@app.get("/health/ready")
async def ready(response: Response) -> dict[str, object]:
    """Return readiness for required infrastructure and local policy configuration."""
    result = await readiness()
    if not result.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if result.ready else "not_ready",
        "checks": result.checks,
    }


def main() -> None:
    """Run the web process."""
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
