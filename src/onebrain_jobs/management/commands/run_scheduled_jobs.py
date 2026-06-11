from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

from django.core.management.base import BaseCommand, CommandError

from onebrain_core.contracts.schemas import GraphAggregationResponse
from onebrain_jobs.graph_aggregation import (
    GraphAggregationJob,
    GraphAggregationJobConfig,
    add_graph_aggregation_arguments,
    format_graph_aggregation_result,
)
from onebrain_jobs.scheduler import ScheduledJobConfig, run_scheduled_job
from onebrain_jobs.status import (
    JOB_NAME_GRAPH_AGGREGATION,
    failed_status_payload,
    finished_status_payload,
    graph_aggregation_config_snapshot,
    graph_aggregation_result_snapshot,
    running_status_payload,
    scheduler_config_snapshot,
    write_job_status,
)


class Command(BaseCommand):
    help = "Run OneBrain Django jobs on an interval."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--job",
            choices=["graph-aggregation"],
            default=os.getenv("ONEBRAIN_SCHEDULED_JOB", "graph-aggregation"),
        )
        parser.add_argument(
            "--interval-seconds",
            type=float,
            default=float(os.getenv("ONEBRAIN_GRAPH_AGGREGATION_INTERVAL_SECONDS", "3600")),
        )
        parser.add_argument("--max-runs", type=int, default=None)
        parser.add_argument(
            "--no-run-immediately",
            action="store_false",
            dest="run_immediately",
            default=True,
        )
        add_graph_aggregation_arguments(parser)

    def handle(self, *args, **options) -> None:
        if options["interval_seconds"] < 0:
            raise CommandError("--interval-seconds must be greater than or equal to 0")
        if options["max_runs"] is not None and options["max_runs"] < 1:
            raise CommandError("--max-runs must be greater than or equal to 1")

        try:
            aggregation_config = GraphAggregationJobConfig.from_options(options)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        scheduler_config = ScheduledJobConfig(
            interval_seconds=options["interval_seconds"],
            max_runs=options["max_runs"],
            run_immediately=options["run_immediately"],
        )
        job = GraphAggregationJob()
        scheduler_payload = scheduler_config_snapshot(scheduler_config)
        config_payload = graph_aggregation_config_snapshot(aggregation_config)

        self.stdout.write(
            "Starting scheduled job "
            f"{options['job']} every {scheduler_config.interval_seconds:g}s "
            f"max_runs={scheduler_config.max_runs or 'infinite'}."
        )

        def on_start(run_count: int, started_at) -> None:
            write_job_status(
                JOB_NAME_GRAPH_AGGREGATION,
                running_status_payload(
                    run_count=run_count,
                    started_at=started_at,
                    scheduler=scheduler_payload,
                    configuration=config_payload,
                ),
            )

        def on_result(
            result: GraphAggregationResponse,
            run_count: int,
            started_at,
        ) -> None:
            finished_at = datetime.now(UTC)
            write_job_status(
                JOB_NAME_GRAPH_AGGREGATION,
                finished_status_payload(
                    run_count=run_count,
                    started_at=started_at,
                    finished_at=finished_at,
                    scheduler=scheduler_payload,
                    configuration=config_payload,
                    result=graph_aggregation_result_snapshot(result),
                ),
            )
            self.stdout.write(f"[run {run_count} at {started_at.isoformat()}]")
            lines = format_graph_aggregation_result(result)
            self.stdout.write(self.style.SUCCESS(lines[0]))
            for line in lines[1:]:
                self.stdout.write(line)

        def on_error(exc: BaseException, run_count: int, started_at) -> None:
            write_job_status(
                JOB_NAME_GRAPH_AGGREGATION,
                failed_status_payload(
                    run_count=run_count,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                    scheduler=scheduler_payload,
                    configuration=config_payload,
                    error=exc,
                ),
            )

        try:
            asyncio.run(
                run_scheduled_job(
                    config=scheduler_config,
                    run_once=lambda: job.run_once(aggregation_config),
                    on_start=on_start,
                    on_result=on_result,
                    on_error=on_error,
                )
            )
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Scheduled jobs stopped."))
