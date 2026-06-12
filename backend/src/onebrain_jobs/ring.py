from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Generic, TypeVar

from onebrain_jobs.scheduler import ScheduledJobConfig, run_scheduled_job
from onebrain_jobs.status import (
    failed_status_payload,
    finished_status_payload,
    running_status_payload,
    scheduler_config_snapshot,
    write_job_status,
)

ConfigT = TypeVar("ConfigT")
ResultT = TypeVar("ResultT")


@dataclass(frozen=True)
class JobDefinition(Generic[ConfigT, ResultT]):
    name: str
    command: str
    run_once: Callable[[ConfigT], Awaitable[ResultT]]
    config_snapshot: Callable[[ConfigT], dict]
    result_snapshot: Callable[[ResultT], dict]
    format_result: Callable[[ResultT], list[str]]


async def execute_job_once(
    *,
    definition: JobDefinition[ConfigT, ResultT],
    config: ConfigT,
    scheduler: ScheduledJobConfig,
    run_count: int = 1,
) -> ResultT:
    started_at = datetime.now(UTC)
    scheduler_payload = scheduler_config_snapshot(scheduler)
    config_payload = definition.config_snapshot(config)
    write_job_status(
        definition.name,
        running_status_payload(
            run_count=run_count,
            started_at=started_at,
            scheduler=scheduler_payload,
            configuration=config_payload,
        ),
    )

    try:
        result = await definition.run_once(config)
    except Exception as exc:
        write_job_status(
            definition.name,
            failed_status_payload(
                run_count=run_count,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                scheduler=scheduler_payload,
                configuration=config_payload,
                error=exc,
            ),
        )
        raise

    write_job_status(
        definition.name,
        finished_status_payload(
            run_count=run_count,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            scheduler=scheduler_payload,
            configuration=config_payload,
            result=definition.result_snapshot(result),
        ),
    )
    return result


async def run_job_on_schedule(
    *,
    definition: JobDefinition[ConfigT, ResultT],
    config: ConfigT,
    scheduler: ScheduledJobConfig,
    on_output: Callable[[ResultT, int, datetime], None] | None = None,
) -> None:
    scheduler_payload = scheduler_config_snapshot(scheduler)
    config_payload = definition.config_snapshot(config)

    def on_start(run_count: int, started_at: datetime) -> None:
        write_job_status(
            definition.name,
            running_status_payload(
                run_count=run_count,
                started_at=started_at,
                scheduler=scheduler_payload,
                configuration=config_payload,
            ),
        )

    def on_result(result: ResultT, run_count: int, started_at: datetime) -> None:
        write_job_status(
            definition.name,
            finished_status_payload(
                run_count=run_count,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                scheduler=scheduler_payload,
                configuration=config_payload,
                result=definition.result_snapshot(result),
            ),
        )
        if on_output is not None:
            on_output(result, run_count, started_at)

    def on_error(exc: BaseException, run_count: int, started_at: datetime) -> None:
        write_job_status(
            definition.name,
            failed_status_payload(
                run_count=run_count,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                scheduler=scheduler_payload,
                configuration=config_payload,
                error=exc,
            ),
        )

    await run_scheduled_job(
        config=scheduler,
        run_once=lambda: definition.run_once(config),
        on_start=on_start,
        on_result=on_result,
        on_error=on_error,
    )
