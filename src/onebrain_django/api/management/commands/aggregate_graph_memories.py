from __future__ import annotations

import asyncio

from django.core.management.base import BaseCommand, CommandError

from onebrain_django.jobs.graph_aggregation import (
    GraphAggregationJob,
    GraphAggregationJobConfig,
    add_graph_aggregation_arguments,
    format_graph_aggregation_result,
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
        result = asyncio.run(GraphAggregationJob().run_once(config))

        lines = format_graph_aggregation_result(result)
        self.stdout.write(self.style.SUCCESS(lines[0]))
        for line in lines[1:]:
            self.stdout.write(line)
