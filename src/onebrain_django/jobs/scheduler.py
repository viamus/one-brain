from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ScheduledJobConfig:
    interval_seconds: float
    max_runs: int | None = None
    run_immediately: bool = True


async def run_scheduled_job(
    *,
    config: ScheduledJobConfig,
    run_once: Callable[[], Awaitable[T]],
    on_result: Callable[[T, int, datetime], None] | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    run_count = 0
    if not config.run_immediately:
        await sleep(config.interval_seconds)

    while config.max_runs is None or run_count < config.max_runs:
        run_count += 1
        started_at = datetime.now(UTC)
        result = await run_once()
        if on_result is not None:
            on_result(result, run_count, started_at)
        if config.max_runs is not None and run_count >= config.max_runs:
            break
        await sleep(config.interval_seconds)
