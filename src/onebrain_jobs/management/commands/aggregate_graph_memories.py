from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from django.core.management.base import BaseCommand, CommandError

from onebrain_jobs.graph_aggregation import (
    GraphAggregationJob,
    GraphAggregationJobConfig,
    add_graph_aggregation_arguments,
    format_graph_aggregation_result,
)
from onebrain_jobs.scheduler import ScheduledJobConfig
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
    help = "Materialize graph grouping opportunities as aggregate OneBrain memories."

    def add_arguments(self, parser) -> None:
        add_graph_aggregation_arguments(parser)

    def handle(self, *args, **options) -> None:
        try:
            config = GraphAggregationJobConfig.from_options(options)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        started_at = datetime.now(UTC)
        scheduler_payload = scheduler_config_snapshot(
            ScheduledJobConfig(interval_seconds=0, max_runs=1, run_immediately=True)
        )
        config_payload = graph_aggregation_config_snapshot(config)
        write_job_status(
            JOB_NAME_GRAPH_AGGREGATION,
            running_status_payload(
                run_count=1,
                started_at=started_at,
                scheduler=scheduler_payload,
                configuration=config_payload,
            ),
        )

        try:
            result = asyncio.run(GraphAggregationJob().run_once(config))
        except Exception as exc:
            write_job_status(
                JOB_NAME_GRAPH_AGGREGATION,
                failed_status_payload(
                    run_count=1,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                    scheduler=scheduler_payload,
                    configuration=config_payload,
                    error=exc,
                ),
            )
            raise

        write_job_status(
            JOB_NAME_GRAPH_AGGREGATION,
            finished_status_payload(
                run_count=1,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                scheduler=scheduler_payload,
                configuration=config_payload,
                result=graph_aggregation_result_snapshot(result),
            ),
        )
        lines = format_graph_aggregation_result(result)
        self.stdout.write(self.style.SUCCESS(lines[0]))
        for line in lines[1:]:
            self.stdout.write(line)
