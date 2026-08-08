"""Shared lifecycle helpers for long-running PLS processes."""

import asyncio


async def wait_forever() -> None:
    """Keep a process event loop alive until the runtime stops it."""
    await asyncio.Event().wait()


def run_forever() -> None:
    """Run the minimal process event loop."""
    try:
        asyncio.run(wait_forever())
    except KeyboardInterrupt:
        pass
