from __future__ import annotations

import asyncio

from django.core.management.base import BaseCommand, CommandError

from onebrain.core.contracts.schemas import GraphAggregationResponse
from onebrain.workers.graph_aggregation import (
    GraphAggregationJob,
    GraphAggregationJobConfig,
    add_graph_aggregation_arguments,
    format_graph_aggregation_result,
)
from onebrain.workers.ring import JobDefinition, execute_job_once
from onebrain.workers.scheduler import ScheduledJobConfig
from onebrain.workers.status import (
    JOB_NAME_GRAPH_AGGREGATION,
    graph_aggregation_config_snapshot,
    graph_aggregation_result_snapshot,
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
        result = asyncio.run(
            execute_job_once(
                definition=_graph_aggregation_definition(GraphAggregationJob()),
                config=config,
                scheduler=ScheduledJobConfig(interval_seconds=0, max_runs=1, run_immediately=True),
            )
        )
        lines = format_graph_aggregation_result(result)
        self.stdout.write(self.style.SUCCESS(lines[0]))
        for line in lines[1:]:
            self.stdout.write(line)


def _graph_aggregation_definition(
    job: GraphAggregationJob,
) -> JobDefinition[GraphAggregationJobConfig, GraphAggregationResponse]:
    return JobDefinition(
        name=JOB_NAME_GRAPH_AGGREGATION,
        command="onebrain-jobs aggregate_graph_memories",
        run_once=job.run_once,
        config_snapshot=graph_aggregation_config_snapshot,
        result_snapshot=graph_aggregation_result_snapshot,
        format_result=format_graph_aggregation_result,
    )
